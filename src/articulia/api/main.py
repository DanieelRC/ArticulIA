"""API HTTP de ArticulIA.

Correr en local: `uv run uvicorn articulia.api.main:app --reload`
Documentación interactiva: http://localhost:8000/docs
"""

import logging
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langgraph.graph.state import CompiledStateGraph

from articulia.agent.graph import pasos, responder
from articulia.agent.state import Respuesta
from articulia.agent.tools import Corpus
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

log = logging.getLogger("articulia.api")

app = FastAPI(
    title="ArticulIA",
    description=(
        "Responde preguntas sobre leyes federales mexicanas citando el artículo exacto. "
        "Si no encuentra evidencia en el corpus, lo dice. No sustituye asesoría legal."
    ),
    version="0.1.0",
)


class ServicioNoDisponible(RuntimeError):
    """Falta configuración (API key) o un servicio externo no responde."""


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


def get_corpus() -> Corpus:
    """Corpus compartido por todas las peticiones."""
    return _corpus()


def get_graph() -> CompiledStateGraph:
    """Grafo compilado del agente (se crea en la primera pregunta)."""
    return _graph()


CorpusDep = Annotated[Corpus, Depends(get_corpus)]
GraphDep = Annotated[CompiledStateGraph, Depends(get_graph)]


# --- Errores ----------------------------------------------------------------------------------


@app.exception_handler(ServicioNoDisponible)
async def _servicio_no_disponible(_: Request, exc: ServicioNoDisponible) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def _error_inesperado(_: Request, exc: Exception) -> JSONResponse:
    log.exception("Error no manejado", exc_info=exc)
    return JSONResponse(
        status_code=500, content={"detail": "Error interno. Revisa los registros del servidor."}
    )


_ERRORES = {503: {"model": ErrorOut, "description": "Falta configuración del LLM o la base."}}


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


def _leyes(req: AskRequest) -> list[str] | None:
    return [ley.value for ley in req.leyes] if req.leyes else None


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
            return {"nodo": nodo, "mensaje": "Citas verificadas"}
        return {
            "nodo": nodo,
            "mensaje": "La verificación encontró problemas; reintentando",
            "problemas": update.get("problemas", []),
        }
    return {"nodo": nodo, "mensaje": "No hay evidencia suficiente"}


# --- Endpoints --------------------------------------------------------------------------------


@app.post("/ask", response_model=AskResponse, responses=_ERRORES, tags=["agente"])
def ask(req: AskRequest, graph: GraphDep) -> AskResponse:
    """Responde una pregunta y devuelve la respuesta con sus citas."""
    return _respuesta_out(responder(req.pregunta, _leyes(req), graph=graph))


@app.post("/ask/stream", response_class=EventSourceResponse, responses=_ERRORES, tags=["agente"])
def ask_stream(req: AskRequest, graph: GraphDep) -> Iterator[ServerSentEvent]:
    """Igual que /ask, pero emite por SSE cada paso del agente y al final la respuesta.

    Eventos: `paso` (uno por nodo), `respuesta` (final) o `error`.
    """
    try:
        for nodo, update in pasos(req.pregunta, _leyes(req), graph=graph):
            yield ServerSentEvent(event="paso", data=describir_paso(nodo, update))
            if update.get("respuesta") is not None:
                final = _respuesta_out(update["respuesta"])
                yield ServerSentEvent(event="respuesta", data=final.model_dump())
    except Exception as exc:  # el stream ya empezó: el error viaja como evento
        log.exception("Error durante /ask/stream", exc_info=exc)
        yield ServerSentEvent(event="error", data={"detail": "Error al generar la respuesta."})


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
