"""Control de gasto y abuso de la API: presupuesto diario, límite por IP, caché y concurrencia.

Cada pregunta al agente cuesta dinero en el proveedor del LLM. Sin estas barreras, cualquiera
que alcance `/ask` puede agotar el saldo. El orden de las comprobaciones va de lo más barato a
lo más caro: límite por IP → caché → presupuesto → cupo de concurrencia.
"""

import hashlib
import json
import threading
import time
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from articulia.config import Settings


class LimiteExcedido(Exception):
    """Se rechaza la consulta (429): demasiadas peticiones o presupuesto agotado."""

    def __init__(self, detalle: str, reintentar_en: int | None = None) -> None:
        super().__init__(detalle)
        self.detalle = detalle
        self.reintentar_en = reintentar_en


class Ocupado(Exception):
    """Todos los cupos de agente están en uso (503)."""


# --- Almacenamiento ------------------------------------------------------------------------------


class Almacen(Protocol):
    """Persistencia del gasto diario y de la caché de respuestas."""

    def gasto_hoy(self) -> float:
        """Costo en USD acumulado hoy."""
        ...

    def sumar_uso(self, entrada: int, salida: int, costo: float) -> None:
        """Agrega tokens y costo al acumulado de hoy."""
        ...

    def cache_leer(self, clave: str) -> dict | None:
        """Respuesta guardada y vigente, o None."""
        ...

    def cache_guardar(self, clave: str, respuesta: dict, ttl_horas: int) -> None:
        """Guarda una respuesta."""
        ...

    def version_corpus(self) -> str:
        """Huella del corpus indexado: si cambia, la caché anterior deja de aplicar."""
        ...


class AlmacenMemoria:
    """Almacén en memoria para pruebas y para correr sin base de datos."""

    def __init__(self) -> None:
        self._gasto: dict[date, float] = defaultdict(float)
        self.tokens: list[tuple[int, int]] = []
        self._cache: dict[str, tuple[dict, float]] = {}

    def gasto_hoy(self) -> float:
        """Ver `Almacen.gasto_hoy`."""
        return self._gasto[datetime.now(UTC).date()]

    def sumar_uso(self, entrada: int, salida: int, costo: float) -> None:
        """Ver `Almacen.sumar_uso`."""
        self._gasto[datetime.now(UTC).date()] += costo
        self.tokens.append((entrada, salida))

    def cache_leer(self, clave: str) -> dict | None:
        """Ver `Almacen.cache_leer`."""
        item = self._cache.get(clave)
        return item[0] if item and item[1] > time.time() else None

    def cache_guardar(self, clave: str, respuesta: dict, ttl_horas: int) -> None:
        """Ver `Almacen.cache_guardar`."""
        self._cache[clave] = (respuesta, time.time() + ttl_horas * 3600)

    def version_corpus(self) -> str:
        """Ver `Almacen.version_corpus`."""
        return "memoria"


_DDL = """
CREATE TABLE IF NOT EXISTS usage_daily (
    day           date PRIMARY KEY,
    input_tokens  bigint  NOT NULL DEFAULT 0,
    output_tokens bigint  NOT NULL DEFAULT 0,
    cost_usd      numeric(12, 6) NOT NULL DEFAULT 0,
    requests      integer NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS answer_cache (
    key        text PRIMARY KEY,
    response   jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
"""


class AlmacenPostgres:
    """Almacén en PostgreSQL: el gasto sobrevive a reinicios del contenedor."""

    def __init__(self, pool: object) -> None:
        self.pool = pool
        self._version: str | None = None
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            conn.execute(_DDL)

    def gasto_hoy(self) -> float:
        """Ver `Almacen.gasto_hoy`."""
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                "SELECT cost_usd FROM usage_daily WHERE day = (now() AT TIME ZONE 'utc')::date"
            ).fetchone()
        return float(row[0]) if row else 0.0

    def sumar_uso(self, entrada: int, salida: int, costo: float) -> None:
        """Ver `Almacen.sumar_uso`. Atómico: varias peticiones pueden sumar a la vez."""
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            conn.execute(
                "INSERT INTO usage_daily (day, input_tokens, output_tokens, cost_usd, requests) "
                "VALUES ((now() AT TIME ZONE 'utc')::date, %s, %s, %s, 1) "
                "ON CONFLICT (day) DO UPDATE SET "
                "input_tokens = usage_daily.input_tokens + EXCLUDED.input_tokens, "
                "output_tokens = usage_daily.output_tokens + EXCLUDED.output_tokens, "
                "cost_usd = usage_daily.cost_usd + EXCLUDED.cost_usd, "
                "requests = usage_daily.requests + 1",
                (entrada, salida, costo),
            )

    def cache_leer(self, clave: str) -> dict | None:
        """Ver `Almacen.cache_leer`."""
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            row = conn.execute(
                "SELECT response FROM answer_cache WHERE key = %s AND expires_at > now()", (clave,)
            ).fetchone()
        return row[0] if row else None

    def cache_guardar(self, clave: str, respuesta: dict, ttl_horas: int) -> None:
        """Ver `Almacen.cache_guardar`. De paso borra las entradas vencidas."""
        with self.pool.connection() as conn:  # type: ignore[attr-defined]
            conn.execute("DELETE FROM answer_cache WHERE expires_at <= now()")
            conn.execute(
                "INSERT INTO answer_cache (key, response, expires_at) "
                "VALUES (%s, %s::jsonb, now() + make_interval(hours => %s)) "
                "ON CONFLICT (key) DO UPDATE SET response = EXCLUDED.response, "
                "created_at = now(), expires_at = EXCLUDED.expires_at",
                (clave, json.dumps(respuesta, ensure_ascii=False), ttl_horas),
            )

    def version_corpus(self) -> str:
        """Ver `Almacen.version_corpus`. Se calcula una vez por proceso."""
        if self._version is None:
            with self.pool.connection() as conn:  # type: ignore[attr-defined]
                row = conn.execute(
                    "SELECT md5(coalesce(string_agg(content_hash, '' ORDER BY id), '')) "
                    "FROM articles"
                ).fetchone()
            self._version = row[0]
        return self._version


# --- Límite por IP -------------------------------------------------------------------------------


class LimiteIP:
    """Ventana deslizante por minuto y contador por día, en memoria y seguro entre hilos."""

    def __init__(self, por_minuto: int, por_dia: int) -> None:
        self.por_minuto = por_minuto
        self.por_dia = por_dia
        self._minuto: dict[str, deque[float]] = defaultdict(deque)
        self._dia: dict[str, tuple[date, int]] = {}
        self._lock = threading.Lock()

    def registrar(self, ip: str, ahora: float | None = None) -> None:
        """Cuenta una petición o lanza `LimiteExcedido` con los segundos de espera."""
        ahora = time.time() if ahora is None else ahora
        hoy = datetime.fromtimestamp(ahora, UTC).date()
        with self._lock:
            ventana = self._minuto[ip]
            while ventana and ventana[0] <= ahora - 60:
                ventana.popleft()
            if len(ventana) >= self.por_minuto:
                espera = int(ventana[0] + 60 - ahora) + 1
                raise LimiteExcedido(
                    f"Demasiadas consultas seguidas. Espera {espera} segundos.", espera
                )
            dia, cuenta = self._dia.get(ip, (hoy, 0))
            if dia != hoy:
                cuenta = 0
            if cuenta >= self.por_dia:
                manana = datetime.combine(hoy + timedelta(days=1), datetime.min.time(), UTC)
                raise LimiteExcedido(
                    "Alcanzaste el máximo de consultas por hoy desde tu conexión. Vuelve mañana.",
                    int(manana.timestamp() - ahora),
                )
            ventana.append(ahora)
            self._dia[ip] = (hoy, cuenta + 1)
            if len(self._dia) > 50_000:  # no crecer sin límite ante muchas IP distintas
                self._dia = {k: v for k, v in self._dia.items() if v[0] == hoy}
                self._minuto = defaultdict(deque, {k: v for k, v in self._minuto.items() if v})


# --- Guardia -------------------------------------------------------------------------------------


def clave_cache(pregunta: str, leyes: list[str] | None, modelo: str, corpus: str) -> str:
    """Clave estable: ignora mayúsculas, acentos, signos y espacios de más en la pregunta."""
    texto = unicodedata.normalize("NFKD", pregunta.lower())
    texto = "".join(c for c in texto if c.isalnum() or c.isspace())
    partes = [" ".join(texto.split()), ",".join(sorted(leyes or [])), modelo, corpus]
    return hashlib.sha256("|".join(partes).encode("utf-8")).hexdigest()


@dataclass
class Admision:
    """Resultado de admitir una consulta: respuesta en caché o cupo para correr el agente."""

    clave: str
    en_cache: dict | None = None
    _liberar: object | None = None

    def liberar(self) -> None:
        """Devuelve el cupo de concurrencia (se puede llamar más de una vez)."""
        if self._liberar is not None:
            self._liberar()  # type: ignore[operator]
            self._liberar = None


class Guardia:
    """Decide si una consulta puede correr y lleva la cuenta de lo que costó."""

    def __init__(self, settings: Settings, almacen: Almacen) -> None:
        self.s = settings
        self.almacen = almacen
        self.ips = LimiteIP(settings.rate_limit_per_minute, settings.rate_limit_per_day)
        self._cupos = threading.BoundedSemaphore(settings.max_concurrent_agents)

    def admitir(self, ip: str, pregunta: str, leyes: list[str] | None) -> Admision:
        """Aplica límite por IP, caché, presupuesto y concurrencia, en ese orden."""
        self.ips.registrar(ip)
        modelo = f"{self.s.llm_provider}/{self.s.llm_model}"
        clave = clave_cache(pregunta, leyes, modelo, self.almacen.version_corpus())
        if self.s.answer_cache_ttl_hours > 0:
            guardada = self.almacen.cache_leer(clave)
            if guardada is not None:
                return Admision(clave, en_cache=guardada)
        if self.almacen.gasto_hoy() >= self.s.daily_budget_usd:
            raise LimiteExcedido(
                "La demo alcanzó su tope de consultas por hoy. Vuelve mañana, o corre el "
                "proyecto en tu equipo con tu propia API key."
            )
        if not self._cupos.acquire(blocking=False):
            raise Ocupado("Hay varias consultas en curso. Intenta de nuevo en unos segundos.")
        return Admision(clave, _liberar=self._cupos.release)

    def costo(self, entrada: int, salida: int) -> float:
        """Costo en USD de una consulta según los precios configurados."""
        return (
            entrada * self.s.llm_price_in_per_m + salida * self.s.llm_price_out_per_m
        ) / 1_000_000

    def cerrar(self, admision: Admision, entrada: int, salida: int, respuesta: dict | None) -> None:
        """Registra el gasto, guarda la respuesta en caché y libera el cupo."""
        try:
            if entrada or salida:
                self.almacen.sumar_uso(entrada, salida, self.costo(entrada, salida))
            if respuesta is not None and self.s.answer_cache_ttl_hours > 0:
                self.almacen.cache_guardar(admision.clave, respuesta, self.s.answer_cache_ttl_hours)
        finally:
            admision.liberar()
