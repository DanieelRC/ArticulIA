"""API HTTP de ArticulIA.

Correr en local: `uv run uvicorn articulia.api.main:app --reload`
Documentación interactiva (solo fuera de producción): http://localhost:8000/docs
"""

import logging
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langgraph.graph.state import CompiledStateGraph

from articulia.agent.graph import pasos
from articulia.agent.state import Respuesta
from articulia.agent.tools import Corpus
from articulia.api.limits import (
    Admision,
    AlmacenMemoria,
    AlmacenPostgres,
    Guardia,
    LimiteExcedido,
    Ocupado,
)
from articulia.api.schemas import (
    ArticleOut,
    AskRequest,
    AskResponse,
    CitaOut,
    ErrorOut,
    HealthOut,
    LawOut,
    Ley,
)
from articulia.config import get_settings

log = logging.getLogger("articulia.api")
_settings = get_settings()
_produccion = _settings.environment == "production"


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Carga los modelos locales en segundo plano para que la primera pregunta no espere."""
    if _settings.warmup_models:

        def calentar() -> None:
            try:
                from articulia.models import embed, get_reranker

                embed(["calentamiento"])
                if _settings.reranker_enabled:
                    get_reranker()
            except Exception:
                log.exception("No se pudieron precargar los modelos")

        threading.Thread(target=calentar, daemon=True).start()
    yield


app = FastAPI(
    title="ArticulIA",
    description=(
        "Responde preguntas sobre leyes federales mexicanas citando el artículo exacto. "
        "Si no encuentra evidencia en el corpus, lo dice. No sustituye asesoría legal."
    ),
    version="0.2.0",
    lifespan=_lifespan,
    # En producción no se publica la documentación interactiva ni el esquema.
    docs_url=None if _produccion else "/docs",
    redoc_url=None if _produccion else "/redoc",
    openapi_url=None if _produccion else "/openapi.json",
)


class ServicioNoDisponible(RuntimeError):
    """Falta configuración (API key) o un servicio externo no responde."""


class TopeDeTokens(RuntimeError):
    """La consulta superó el máximo de tokens permitido y se cortó."""


# --- Dependencias (se sustituyen en pruebas con app.dependency_overrides) ---------------------


@lru_cache
def _corpus() -> Corpus:
    from articulia.agent.tools import PostgresCorpus

    return PostgresCorpus()


@lru_cache
def _graph() -> CompiledStateGraph:
    from articulia.agent.graph import build_graph

    try:
        return build_graph(corpus=_corpus())
    except RuntimeError as exc:  # p. ej. falta la API key del LLM
        raise ServicioNoDisponible(str(exc)) from exc


@lru_cache
def _guardia() -> Guardia:
    try:
        almacen = AlmacenPostgres(_corpus().pool)  # type: ignore[attr-defined]
    except Exception:
        # Sin base no hay dónde llevar la cuenta; en producción eso es motivo para no atender.
        if _produccion:
            raise
        log.warning("Sin base de datos: el presupuesto y la caché viven en memoria")
        almacen = AlmacenMemoria()
    return Guardia(get_settings(), almacen)


def get_corpus() -> Corpus:
    """Corpus compartido por todas las peticiones."""
    return _corpus()


def get_graph() -> CompiledStateGraph:
    """Grafo compilado del agente (se crea en la primera pregunta)."""
    return _graph()


def get_guardia() -> Guardia:
    """Control de gasto y abuso compartido por todas las peticiones."""
    return _guardia()


def _leyes(req: AskRequest) -> list[str] | None:
    return [ley.value for ley in req.leyes] if req.leyes else None


def admitir(
    req: AskRequest, request: Request, guardia: Annotated[Guardia, Depends(get_guardia)]
) -> Admision:
    """Corre antes de responder: aquí todavía se puede contestar 429 o 503.

    La IP es la del cliente que ve uvicorn; detrás del proxy se toma de X-Forwarded-For solo
    si uvicorn se arrancó con `--proxy-headers` y el proxy es de confianza.
    """
    ip = request.client.host if request.client else "desconocida"
    return guardia.admitir(ip, req.pregunta, _leyes(req))


CorpusDep = Annotated[Corpus, Depends(get_corpus)]
GraphDep = Annotated[CompiledStateGraph, Depends(get_graph)]
GuardiaDep = Annotated[Guardia, Depends(get_guardia)]
AdmisionDep = Annotated[Admision, Depends(admitir)]


# --- Errores ----------------------------------------------------------------------------------


@app.exception_handler(ServicioNoDisponible)
async def _servicio_no_disponible(_: Request, exc: ServicioNoDisponible) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(LimiteExcedido)
async def _limite_excedido(_: Request, exc: LimiteExcedido) -> JSONResponse:
    headers = {"Retry-After": str(exc.reintentar_en)} if exc.reintentar_en else None
    return JSONResponse(status_code=429, content={"detail": exc.detalle}, headers=headers)


@app.exception_handler(Ocupado)
async def _ocupado(_: Request, exc: Ocupado) -> JSONResponse:
    return JSONResponse(
        status_code=503, content={"detail": str(exc)}, headers={"Retry-After": "10"}
    )


@app.exception_handler(Exception)
async def _error_inesperado(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Error no manejado", exc_info=exc)
    return JSONResponse(
        status_code=500, content={"detail": "Error interno. Revisa los registros del servidor."}
    )


_ERRORES = {
    429: {"model": ErrorOut, "description": "Límite por IP o tope de gasto diario alcanzado."},
    503: {"model": ErrorOut, "description": "Servicio ocupado o sin configurar."},
}


# --- Conversión -------------------------------------------------------------------------------


def _cita_out(cita: object) -> CitaOut:
    return CitaOut(
        id=cita.article_id,  # type: ignore[attr-defined]
        ley=cita.ley,  # type: ignore[attr-defined]
        numero=cita.numero,  # type: ignore[attr-defined]
        etiqueta=cita.etiqueta(),  # type: ignore[attr-defined]
        url=f"/articles/{cita.ley}/{quote(cita.numero)}",  # type: ignore[attr-defined]
    )


def _respuesta_out(resp: Respuesta) -> AskResponse:
    return AskResponse(
        respuesta=resp.respuesta,
        citas=[_cita_out(c) for c in resp.citas],
        sin_evidencia=resp.sin_evidencia,
    )


def describir_paso(nodo: str, update: dict) -> dict:
    """Resume una actualización del grafo en un mensaje corto para la interfaz."""
    if nodo == "razonar":
        ultimo = update["messages"][-1]
        llamadas = getattr(ultimo, "tool_calls", None) or []
        if llamadas:
            return {
                "nodo": nodo,
                "mensaje": "Buscando en el corpus",
                "herramientas": [{"nombre": c["name"], "args": c["args"]} for c in llamadas],
            }
        return {"nodo": nodo, "mensaje": "Ya tengo suficiente para responder"}
    if nodo == "herramientas":
        ids = list(update.get("articulos", {}))
        return {"nodo": nodo, "mensaje": f"{len(ids)} artículos recuperados", "articulos": ids}
    if nodo == "generar":
        return {"nodo": nodo, "mensaje": "Redactando la respuesta con citas"}
    if nodo == "verificar":
        if update.get("respuesta") is not None:
            return {"nodo": nodo, "mensaje": "Citas cotejadas"}
        return {
            "nodo": nodo,
            "mensaje": "La verificación encontró problemas; reintentando",
            "problemas": update.get("problemas", []),
        }
    return {"nodo": nodo, "mensaje": "No hay evidencia suficiente"}


# --- Ejecución del agente con control de gasto ------------------------------------------------


def _tokens(uso: object) -> tuple[int, int]:
    """Suma tokens de entrada y salida de todos los modelos usados en la consulta."""
    datos = getattr(uso, "usage_metadata", {}) or {}
    return (
        sum(u.get("input_tokens", 0) for u in datos.values()),
        sum(u.get("output_tokens", 0) for u in datos.values()),
    )


def correr(
    req: AskRequest, graph: CompiledStateGraph, guardia: Guardia, admision: Admision
) -> Iterator[tuple[str, dict]]:
    """Corre el agente, corta si pasa el tope de tokens y al terminar registra lo gastado.

    Produce los mismos pares que `pasos`. El bloque `finally` se ejecuta aunque el cliente se
    desconecte (el generador se cierra), así que el gasto siempre se cuenta y el cupo se libera.
    """
    final: AskResponse | None = None
    # Contador explícito (no el de contextvars): este generador se recorre desde varios hilos
    # del pool cuando la respuesta es un stream, y una variable de contexto no los cruza.
    uso = UsageMetadataCallbackHandler()
    try:
        for nodo, update in pasos(req.pregunta, _leyes(req), graph=graph, callbacks=[uso]):
            yield nodo, update
            if nodo != "token" and update.get("respuesta") is not None:
                final = _respuesta_out(update["respuesta"])
            if sum(_tokens(uso)) > guardia.s.max_tokens_per_query:
                raise TopeDeTokens("La consulta superó el máximo de tokens y se detuvo.")
    finally:
        entrada, salida = _tokens(uso)
        guardia.cerrar(admision, entrada, salida, final.model_dump() if final else None)


# --- Endpoints --------------------------------------------------------------------------------


@app.post("/ask", response_model=AskResponse, responses=_ERRORES, tags=["agente"])
def ask(
    req: AskRequest, admision: AdmisionDep, guardia: GuardiaDep, request: Request
) -> AskResponse:
    """Responde una pregunta y devuelve la respuesta con sus citas."""
    if admision.en_cache is not None:
        return AskResponse(**admision.en_cache)
    try:
        graph = request.app.dependency_overrides.get(get_graph, get_graph)()
    except BaseException:
        admision.liberar()
        raise
    final: AskResponse | None = None
    for nodo, update in correr(req, graph, guardia, admision):
        if nodo != "token" and update.get("respuesta") is not None:
            final = _respuesta_out(update["respuesta"])
    if final is None:
        raise RuntimeError("El agente terminó sin respuesta")
    return final


@app.post("/ask/stream", response_class=EventSourceResponse, responses=_ERRORES, tags=["agente"])
def ask_stream(
    req: AskRequest, admision: AdmisionDep, guardia: GuardiaDep, request: Request
) -> Iterator[ServerSentEvent]:
    """Igual que /ask, pero emite por SSE cada paso del agente y al final la respuesta.

    Eventos: `paso` (uno por nodo), `token` (texto de la respuesta mientras se escribe),
    `borrador_descartado` (el verificador rechazó lo escrito; hay que limpiar el texto),
    `respuesta` (final, ya verificada) o `error`.
    """
    if admision.en_cache is not None:
        yield ServerSentEvent(
            event="paso",
            data={"nodo": "cache", "mensaje": "Respuesta ya cotejada de una consulta idéntica"},
        )
        yield ServerSentEvent(event="respuesta", data=admision.en_cache)
        return
    try:
        graph = request.app.dependency_overrides.get(get_graph, get_graph)()
        for nodo, update in correr(req, graph, guardia, admision):
            if nodo == "token":
                yield ServerSentEvent(event="token", data=update)
                continue
            yield ServerSentEvent(event="paso", data=describir_paso(nodo, update))
            if nodo == "verificar" and update.get("respuesta") is None:
                yield ServerSentEvent(
                    event="borrador_descartado", data={"problemas": update.get("problemas", [])}
                )
            if nodo == "abstenerse":
                yield ServerSentEvent(event="borrador_descartado", data={"problemas": []})
            if update.get("respuesta") is not None:
                final = _respuesta_out(update["respuesta"])
                yield ServerSentEvent(event="respuesta", data=final.model_dump())
    except ServicioNoDisponible as exc:
        yield ServerSentEvent(event="error", data={"detail": str(exc), "status": 503})
    except TopeDeTokens as exc:
        yield ServerSentEvent(event="error", data={"detail": str(exc), "status": 500})
    except Exception as exc:  # el stream ya empezó: el error viaja como evento
        log.exception("Error durante /ask/stream", exc_info=exc)
        yield ServerSentEvent(event="error", data={"detail": "Error al generar la respuesta."})
    finally:
        admision.liberar()


@app.get("/laws", response_model=list[LawOut], tags=["corpus"])
def laws(corpus: CorpusDep) -> list[dict]:
    """Leyes del corpus con su número de artículos y fecha de última reforma."""
    return corpus.leyes()  # type: ignore[attr-defined]


@app.get(
    "/articles/{ley}/{numero}",
    response_model=ArticleOut,
    responses={404: {"model": ErrorOut}},
    tags=["corpus"],
)
def article(ley: Ley, numero: str, corpus: CorpusDep) -> dict:
    """Texto completo de un artículo, p. ej. `/articles/LFT/61` o `/articles/LFT/47 Bis`."""
    if len(numero) > 30:
        raise HTTPException(422, "Número de artículo demasiado largo.")
    art = corpus.obtener(ley.value, numero)
    if art is None:
        raise HTTPException(404, f"No existe el artículo {numero} en {ley.value}.")
    return art


@app.get("/health", response_model=HealthOut, tags=["servicio"])
def health(corpus: CorpusDep) -> JSONResponse:
    """Estado del servicio y de la base de datos (503 si la base no responde)."""
    ok = corpus.ping()  # type: ignore[attr-defined]
    body = HealthOut(status="ok" if ok else "degradado", db=ok)
    return JSONResponse(status_code=200 if ok else 503, content=body.model_dump())
