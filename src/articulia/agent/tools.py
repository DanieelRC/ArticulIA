"""Herramientas del agente: buscar, obtener un artículo y comparar entre leyes.

Las funciones reciben un `Corpus` para poder probarse sin base de datos. El agente y el servidor MCP
(Fase 8) usan las mismas funciones.
"""

import re
import threading
from collections import OrderedDict
from typing import Protocol

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from articulia.ingest.loader import LEYES


class Corpus(Protocol):
    """Acceso al corpus indexado."""

    def buscar(self, consulta: str, leyes: list[str] | None, top_k: int) -> list[dict]:
        """Artículos relevantes para la consulta."""
        ...

    def obtener(self, ley: str, numero: str) -> dict | None:
        """Un artículo por ley y número, o None si no existe."""
        ...


class PostgresCorpus:
    """Corpus respaldado por PostgreSQL (búsqueda híbrida + reranker).

    Usa un pool de conexiones: la API atiende peticiones en varios hilos y una conexión de
    psycopg no debe compartirse entre consultas simultáneas.
    """

    MAX_BUSQUEDAS = 512

    def __init__(self, max_size: int = 4) -> None:
        from pgvector.psycopg import register_vector
        from psycopg_pool import ConnectionPool

        from articulia.config import get_settings

        self.pool = ConnectionPool(
            get_settings().database_url,
            min_size=1,
            max_size=max_size,
            kwargs={"autocommit": True},
            timeout=10,  # si la base no responde, fallar pronto con un error claro
            configure=register_vector,
            open=True,
        )
        self._busquedas: OrderedDict[tuple, list[dict]] = OrderedDict()
        self._lock = threading.Lock()

    def buscar(self, consulta: str, leyes: list[str] | None, top_k: int) -> list[dict]:
        """Ver `articulia.retrieval.rerank.search`."""
        from articulia.retrieval.rerank import search

        # Caché en proceso: el agente y distintos usuarios repiten búsquedas, y cada una cuesta
        # un embedding y un reranking. El corpus no cambia mientras el proceso vive.
        clave = (" ".join(consulta.lower().split()), tuple(sorted(leyes or [])), top_k)
        with self._lock:
            if clave in self._busquedas:
                self._busquedas.move_to_end(clave)
                return [dict(r) for r in self._busquedas[clave]]
        with self.pool.connection() as conn:
            resultado = [r.model_dump(mode="json") for r in search(conn, consulta, leyes, top_k)]
        with self._lock:
            self._busquedas[clave] = resultado
            while len(self._busquedas) > self.MAX_BUSQUEDAS:
                self._busquedas.popitem(last=False)
        return [dict(r) for r in resultado]

    def obtener(self, ley: str, numero: str) -> dict | None:
        """Busca por ley y número ('5o', '123 bis', '39-a'); permanentes antes que transitorios."""
        numero = re.sub(r"^(\d+)\s*[oº°]?\.?$", r"\1", numero.strip())  # '5o.' -> '5'
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT id, ley, ley_nombre, numero, tipo, titulo, capitulo, seccion, texto, url, "
                "fecha_ultima_reforma, derogado, reformas FROM articles "
                "WHERE ley = %s AND lower(numero) = lower(%s) ORDER BY tipo LIMIT 1",
                (ley.upper(), numero.replace("_", " ")),
            ).fetchone()
        if row is None:
            return None
        cols = ("id", "ley", "ley_nombre", "numero", "tipo", "titulo", "capitulo", "seccion",
                "texto", "url", "fecha_ultima_reforma", "derogado", "reformas")  # fmt: skip
        art = dict(zip(cols, row, strict=True))
        fecha = art["fecha_ultima_reforma"]
        art["fecha_ultima_reforma"] = fecha.isoformat() if fecha else None
        return art

    def leyes(self) -> list[dict]:
        """Leyes indexadas con su número de artículos vigentes y fecha de última reforma."""
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT ley, ley_nombre, "
                "count(*) FILTER (WHERE tipo = 'articulo' AND NOT derogado), "
                "max(fecha_ultima_reforma), max(url) FROM articles "
                "GROUP BY ley, ley_nombre ORDER BY ley"
            ).fetchall()
        return [
            {"clave": r[0], "nombre": r[1], "articulos": r[2],
             "fecha_ultima_reforma": r[3].isoformat() if r[3] else None, "url": r[4]}
            for r in rows
        ]  # fmt: skip

    def ping(self) -> bool:
        """True si la base responde."""
        try:
            with self.pool.connection(timeout=2) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:
            return False


MAX_CHARS_ARTICULO = 2500


def texto_para_llm(art: dict, limite: int = MAX_CHARS_ARTICULO) -> tuple[str, bool]:
    """Texto del artículo que se envía al modelo y si quedó recortado.

    Hay artículos de decenas de miles de caracteres (CPEUM 123, LFT 513). Mandarlos completos
    multiplica el costo de cada llamada, así que de los largos solo va el fragmento que la
    búsqueda encontró más parecido a la consulta, o el inicio si no hay fragmento. La interfaz
    sigue mostrando el artículo completo; esto solo acota lo que lee el LLM.
    """
    texto = art.get("texto", "").replace("</articulo>", "")
    if len(texto) <= limite:
        return texto, False
    fragmento = (art.get("fragmento") or "").replace("</articulo>", "")
    if fragmento:
        # El fragmento indexado empieza con una línea de contexto (ley, artículo, capítulo).
        cuerpo = fragmento.split("\n", 1)[-1]
        return f"[…]\n{cuerpo[:limite]}\n[…]", True
    return f"{texto[:limite]}\n[…]", True


def formatear_articulo(art: dict) -> str:
    """Representa un artículo como DATOS delimitados, nunca como instrucciones.

    El texto recuperado va dentro de etiquetas <articulo>; el prompt del sistema indica que lo que
    está dentro de esas etiquetas es material de consulta y no órdenes (defensa básica contra
    prompt injection a través del corpus).
    """
    tipo = "transitorio" if art.get("tipo") == "transitorio" else "art."
    cita = f"[{art['ley']}, {tipo} {art['numero']}]"
    ubicacion = " · ".join(x for x in (art.get("titulo"), art.get("capitulo")) if x)
    texto, recortado = texto_para_llm(art)
    aviso = ' recortado="si"' if recortado else ""
    return (
        f'<articulo id="{art["id"]}" cita="{cita}" ley="{art.get("ley_nombre", art["ley"])}"'
        f' ubicacion="{ubicacion}"{aviso}>\n{texto}\n</articulo>'
    )


# --- Esquemas de entrada (validan lo que manda el LLM) ---------------------------------------

_CLAVES = ", ".join(LEYES)


class BuscarArgs(BaseModel):
    consulta: str = Field(description="Qué buscar, en lenguaje natural o términos legales.")
    ley: str | None = Field(default=None, description=f"Filtrar por una ley: {_CLAVES}.")


class ObtenerArgs(BaseModel):
    ley: str = Field(description=f"Clave de la ley: {_CLAVES}.")
    numero: str = Field(description="Número del artículo, p. ej. '61', '123', '47 Bis', '39-A'.")


class CompararArgs(BaseModel):
    tema: str = Field(description="Tema a comparar entre leyes.")
    leyes: list[str] = Field(description=f"Dos o más claves de ley: {_CLAVES}.", min_length=2)


def buscar_articulos(corpus: Corpus, consulta: str, ley: str | None = None) -> list[dict]:
    """Búsqueda híbrida en el corpus, opcionalmente filtrada por ley."""
    leyes = [ley.upper()] if ley else None
    return corpus.buscar(consulta, leyes, 5)


def obtener_articulo(corpus: Corpus, ley: str, numero: str) -> list[dict]:
    """Texto completo de un artículo concreto (lista vacía si no existe)."""
    art = corpus.obtener(ley.upper(), numero)
    return [art] if art else []


def comparar(corpus: Corpus, tema: str, leyes: list[str]) -> list[dict]:
    """Los 3 artículos más relevantes sobre un tema en cada ley indicada."""
    out: list[dict] = []
    for ley in leyes:
        out.extend(corpus.buscar(tema, [ley.upper()], 3))
    return out


TOOL_FUNCS = {
    "buscar_articulos": (buscar_articulos, BuscarArgs),
    "obtener_articulo": (obtener_articulo, ObtenerArgs),
    "comparar": (comparar, CompararArgs),
}


def tool_schemas() -> list[StructuredTool]:
    """Definiciones de herramientas para `bind_tools` (la ejecución la hace el nodo de tools)."""
    return [
        StructuredTool.from_function(
            func=lambda **_: None,
            name=name,
            description=(func.__doc__ or "").strip().splitlines()[0],
            args_schema=schema,
        )
        for name, (func, schema) in TOOL_FUNCS.items()
    ]


def run_tool(corpus: Corpus, name: str, args: dict) -> list[dict]:
    """Valida los argumentos del LLM y ejecuta la herramienta."""
    if name not in TOOL_FUNCS:
        raise ValueError(f"Herramienta desconocida: {name}")
    func, schema = TOOL_FUNCS[name]
    parsed = schema.model_validate(args)
    return func(corpus, **parsed.model_dump())
