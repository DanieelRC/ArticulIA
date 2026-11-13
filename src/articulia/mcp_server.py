"""Servidor MCP de ArticulIA (transporte stdio).

Expone a cualquier cliente MCP (Claude Desktop, Claude Code, etc.) las mismas funciones que usa
el agente: `buscar_articulos`, `obtener_articulo` y `preguntar`.

Correr: `uv run articulia-mcp` (o `uv run python -m articulia.mcp_server`).

En stdio, la salida estándar es el canal del protocolo: nada de este proceso debe escribir ahí.
Los registros y las barras de progreso van a stderr.
"""

import logging
import os
import sys
from typing import Annotated, Any

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from articulia.agent.tools import Corpus, texto_para_llm
from articulia.ingest.loader import LEYES

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
log = logging.getLogger("articulia.mcp")

MAX_CONSULTA = 500
MAX_TEXTO_ARTICULO = 20_000  # tope al devolver un artículo completo (LFT 513 mide 288 mil)
_CLAVES = ", ".join(LEYES)

servidor = MCPServer(
    "articulia",
    title="ArticulIA",
    instructions=(
        "Consulta leyes federales mexicanas vigentes: Constitución (CPEUM), Ley Federal del "
        "Trabajo (LFT), Código Civil Federal (CCF), protección de datos personales (LFPDPPP), "
        "derecho de autor (LFDA) y protección al consumidor (LFPC). Cita siempre el artículo "
        "con el formato que devuelven las herramientas, por ejemplo [LFT, art. 61]. Si las "
        "herramientas no encuentran fundamento, dilo; no completes con conocimiento propio. "
        "No sustituye asesoría legal."
    ),
)


# --- Dependencias perezosas (se sustituyen en pruebas con `configurar`) -----------------------

_deps: dict[str, Any] = {}


def configurar(**deps: Any) -> None:
    """Inyecta `corpus`, `graph` o `guardia` (pruebas). Sin argumentos, limpia lo inyectado."""
    if not deps:
        _deps.clear()
    _deps.update(deps)


def _corpus() -> Corpus:
    if "corpus" not in _deps:
        from articulia.agent.tools import PostgresCorpus

        _deps["corpus"] = PostgresCorpus()
    return _deps["corpus"]


def _graph() -> Any:
    if "graph" not in _deps:
        from articulia.agent.graph import build_graph

        _deps["graph"] = build_graph(corpus=_corpus())
    return _deps["graph"]


def _guardia() -> Any:
    if "guardia" not in _deps:
        from articulia.api.limits import AlmacenPostgres, Guardia
        from articulia.config import get_settings

        _deps["guardia"] = Guardia(get_settings(), AlmacenPostgres(_corpus().pool))  # type: ignore[attr-defined]
    return _deps["guardia"]


# --- Validación y formato ---------------------------------------------------------------------


def _ley(valor: str) -> str:
    clave = valor.strip().upper()
    if clave not in LEYES:
        raise ToolError(f"Ley desconocida: {valor!r}. Las disponibles son: {_CLAVES}.")
    return clave


def _texto(valor: str, nombre: str) -> str:
    limpio = " ".join(valor.split())
    if len(limpio) < 3:
        raise ToolError(f"El campo `{nombre}` está vacío o es demasiado corto.")
    if len(limpio) > MAX_CONSULTA:
        raise ToolError(f"El campo `{nombre}` no puede pasar de {MAX_CONSULTA} caracteres.")
    return limpio


def _cita(art: dict) -> str:
    tipo = "transitorio" if art.get("tipo") == "transitorio" else "art."
    return f"[{art['ley']}, {tipo} {art['numero']}]"


def _resumen(art: dict) -> dict:
    """Un resultado de búsqueda: lo necesario para citar, con el texto acotado."""
    texto, recortado = texto_para_llm(art)
    return {
        "id": art["id"],
        "cita": _cita(art),
        "ley": art.get("ley_nombre", art["ley"]),
        "ubicacion": " · ".join(x for x in (art.get("titulo"), art.get("capitulo")) if x),
        "texto": texto,
        "recortado": recortado,
    }


def _base_no_disponible(exc: Exception) -> ToolError:
    log.exception("Fallo al consultar el corpus", exc_info=exc)
    return ToolError(
        "No se pudo consultar la base de datos de ArticulIA. Verifica que esté levantada "
        "(`docker compose up -d db`) y que el corpus esté indexado."
    )


# --- Lógica (síncrona y probada sin protocolo) ------------------------------------------------


def buscar(consulta: str, ley: str | None = None) -> list[dict]:
    """Búsqueda híbrida en el corpus."""
    consulta = _texto(consulta, "consulta")
    leyes = [_ley(ley)] if ley else None
    try:
        resultados = _corpus().buscar(consulta, leyes, 5)
    except ToolError:
        raise
    except Exception as exc:
        raise _base_no_disponible(exc) from exc
    return [_resumen(a) for a in resultados]


def obtener(ley: str, numero: str) -> dict:
    """Texto completo de un artículo."""
    clave = _ley(ley)
    numero = numero.strip()
    if not numero or len(numero) > 30:
        raise ToolError("Indica el número del artículo, por ejemplo '61', '47 Bis' o '39-A'.")
    try:
        art = _corpus().obtener(clave, numero)
    except Exception as exc:
        raise _base_no_disponible(exc) from exc
    if art is None:
        raise ToolError(f"No existe el artículo {numero} en {clave} ({LEYES[clave]}).")
    texto = art["texto"]
    recortado = len(texto) > MAX_TEXTO_ARTICULO
    return {
        "id": art["id"],
        "cita": _cita(art),
        "ley": art.get("ley_nombre", clave),
        "ubicacion": " · ".join(x for x in (art.get("titulo"), art.get("capitulo")) if x),
        "derogado": bool(art.get("derogado")),
        "texto": texto[:MAX_TEXTO_ARTICULO],
        "recortado": recortado,
        "fecha_ultima_reforma": art.get("fecha_ultima_reforma"),
        "url_pdf": art.get("url"),
    }


def responder_pregunta(pregunta: str, leyes: list[str] | None = None) -> dict:
    """Corre el agente completo, con el mismo control de gasto que la API."""
    from langchain_core.callbacks import UsageMetadataCallbackHandler

    from articulia.agent.graph import pasos
    from articulia.api.limits import LimiteExcedido, Ocupado

    pregunta = _texto(pregunta, "pregunta")
    claves = [_ley(x) for x in leyes] if leyes else None
    try:
        guardia = _guardia()
        admision = guardia.admitir("mcp", pregunta, claves)
    except (LimiteExcedido, Ocupado) as exc:
        raise ToolError(str(exc)) from exc
    except ToolError:
        raise
    except Exception as exc:
        raise _base_no_disponible(exc) from exc
    if admision.en_cache is not None:
        return _salida(admision.en_cache)

    uso = UsageMetadataCallbackHandler()
    final: dict | None = None
    try:
        for nodo, update in pasos(pregunta, claves, graph=_graph(), callbacks=[uso]):
            resp = update.get("respuesta") if nodo != "token" else None
            if resp is not None:
                final = {
                    "respuesta": resp.respuesta,
                    "citas": [{"id": c.article_id, "etiqueta": c.etiqueta()} for c in resp.citas],
                    "sin_evidencia": resp.sin_evidencia,
                }
    except RuntimeError as exc:  # p. ej. falta la API key del LLM
        raise ToolError(str(exc)) from exc
    finally:
        datos = uso.usage_metadata.values()
        guardia.cerrar(
            admision,
            sum(u.get("input_tokens", 0) for u in datos),
            sum(u.get("output_tokens", 0) for u in datos),
            final,
        )
    if final is None:
        raise ToolError("El agente terminó sin respuesta.")
    return _salida(final)


def _salida(resp: dict) -> dict:
    return {
        "respuesta": resp["respuesta"],
        "citas": [c.get("etiqueta") or c.get("id") for c in resp.get("citas", [])],
        "sin_evidencia": bool(resp.get("sin_evidencia")),
    }


# --- Herramientas MCP -------------------------------------------------------------------------
# Son asíncronas y delegan a un hilo: la búsqueda y el agente bloquean varios segundos y el
# servidor debe seguir respondiendo al protocolo mientras tanto.


@servidor.tool(title="Buscar artículos")
async def buscar_articulos(
    consulta: Annotated[str, Field(description="Qué buscar, en lenguaje natural.")],
    ley: Annotated[str | None, Field(description=f"Limitar a una ley. Claves: {_CLAVES}.")] = None,
) -> list[dict]:
    """Busca en las leyes federales mexicanas los 5 artículos más relevantes para un tema.

    Devuelve cada artículo con su cita lista para usar, por ejemplo [LFT, art. 61]. No usa LLM:
    es rápida y no tiene costo.
    """
    return await anyio.to_thread.run_sync(buscar, consulta, ley)


@servidor.tool(title="Obtener un artículo")
async def obtener_articulo(
    ley: Annotated[str, Field(description=f"Clave de la ley: {_CLAVES}.")],
    numero: Annotated[str, Field(description="Número del artículo: '61', '47 Bis', '39-A'.")],
) -> dict:
    """Devuelve el texto vigente y completo de un artículo concreto, con su ubicación en la ley."""
    return await anyio.to_thread.run_sync(obtener, ley, numero)


@servidor.tool(title="Preguntar al agente")
async def preguntar(
    pregunta: Annotated[str, Field(description="La duda legal, con las palabras del usuario.")],
    leyes: Annotated[
        list[str] | None, Field(description=f"Limitar a estas leyes. Claves: {_CLAVES}.")
    ] = None,
) -> dict:
    """Responde una pregunta con el agente de ArticulIA: busca, redacta con citas y las coteja.

    Si no hay fundamento en el corpus devuelve `sin_evidencia: true`. Usa el LLM configurado en
    ArticulIA, así que tarda más y tiene costo; para solo leer la ley, usa las otras herramientas.
    """
    return await anyio.to_thread.run_sync(responder_pregunta, pregunta, leyes)


def main() -> None:
    """Arranca el servidor por stdio."""
    servidor.run("stdio")


if __name__ == "__main__":
    main()
