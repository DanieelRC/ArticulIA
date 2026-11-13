"""Pruebas del servidor MCP con un cliente MCP en memoria, LLM simulado y corpus de la LFT."""

import json
from collections.abc import Iterator
from typing import Any

import anyio
import pytest
from fakes import LFT_59, LFT_61, FakeCorpus, FakeLLM, _art, _tool_call
from langchain_core.messages import AIMessage
from mcp import Client

from articulia import mcp_server
from articulia.agent.graph import build_graph
from articulia.agent.state import Respuesta, Verificacion
from articulia.api.limits import AlmacenMemoria, Guardia
from articulia.config import Settings

RESPUESTA = Respuesta(
    respuesta="La jornada ordinaria no puede pasar de cuarenta horas semanales [LFT, art. 59]."
)


def _llm() -> FakeLLM:
    return FakeLLM(
        razonar=[
            _tool_call("buscar_articulos", {"consulta": "jornada máxima"}),
            AIMessage("LISTO"),
        ],
        respuestas=[RESPUESTA],
        verificaciones=[Verificacion(respaldada=True)],
    )


@pytest.fixture
def entorno() -> Iterator[dict[str, Any]]:
    corpus = FakeCorpus([LFT_59, LFT_61])
    guardia = Guardia(Settings(_env_file=None), AlmacenMemoria())
    deps = {"corpus": corpus, "graph": build_graph(_llm(), corpus), "guardia": guardia}
    mcp_server.configurar(**deps)
    yield deps
    mcp_server.configurar()


def _llamar(nombre: str, argumentos: dict) -> tuple[bool, Any]:
    """Llama una herramienta por el protocolo MCP y devuelve (es_error, contenido)."""

    async def correr() -> tuple[bool, Any]:
        async with Client(mcp_server.servidor) as cliente:
            r = await cliente.call_tool(nombre, argumentos)
            textos = [c.text for c in r.content if getattr(c, "text", None)]
            if r.is_error:
                return True, " ".join(textos)
            return False, [json.loads(t) for t in textos]

    return anyio.run(correr)


def test_expone_las_tres_herramientas_con_descripcion(entorno: dict) -> None:
    async def listar() -> dict[str, Any]:
        async with Client(mcp_server.servidor) as cliente:
            return {t.name: t for t in (await cliente.list_tools()).tools}

    tools = anyio.run(listar)
    assert set(tools) == {"buscar_articulos", "obtener_articulo", "preguntar"}
    assert all(t.description for t in tools.values())
    assert tools["obtener_articulo"].input_schema["required"] == ["ley", "numero"]


def test_buscar_articulos_devuelve_citas_listas(entorno: dict) -> None:
    error, resultados = _llamar("buscar_articulos", {"consulta": "jornada máxima", "ley": "lft"})
    assert not error
    assert [r["cita"] for r in resultados] == ["[LFT, art. 59]", "[LFT, art. 61]"]
    assert resultados[1]["texto"].startswith("La duración de la jornada diaria")
    assert entorno["corpus"].llamadas == [("buscar", ("jornada máxima", ["LFT"]))]


def test_obtener_articulo(entorno: dict) -> None:
    error, [art] = _llamar("obtener_articulo", {"ley": "LFT", "numero": "61"})
    assert not error
    assert art["cita"] == "[LFT, art. 61]"
    assert art["recortado"] is False
    assert "ocho horas la diurna" in art["texto"]


@pytest.mark.parametrize(
    ("herramienta", "argumentos", "mensaje"),
    [
        ("obtener_articulo", {"ley": "LEYX", "numero": "1"}, "Ley desconocida"),
        ("obtener_articulo", {"ley": "LFT", "numero": "9999"}, "No existe el artículo 9999"),
        ("obtener_articulo", {"ley": "LFT", "numero": " "}, "Indica el número"),
        ("buscar_articulos", {"consulta": "  "}, "demasiado corto"),
        ("buscar_articulos", {"consulta": "x" * 501}, "500 caracteres"),
        ("buscar_articulos", {"consulta": "jornada", "ley": "ISR"}, "Ley desconocida"),
        ("preguntar", {"pregunta": "¿Jornada?", "leyes": ["LFT", "NADA"]}, "Ley desconocida"),
    ],
)
def test_errores_claros(entorno: dict, herramienta: str, argumentos: dict, mensaje: str) -> None:
    error, texto = _llamar(herramienta, argumentos)
    assert error
    assert mensaje in texto


def test_base_caida_da_un_error_entendible() -> None:
    class CorpusCaido:
        def buscar(self, *_: Any) -> list[dict]:
            raise ConnectionError("connection refused")

    mcp_server.configurar(corpus=CorpusCaido())
    try:
        error, texto = _llamar("buscar_articulos", {"consulta": "jornada máxima"})
    finally:
        mcp_server.configurar()
    assert error
    assert "docker compose up -d db" in texto
    assert "connection refused" not in texto  # sin detalles internos


def test_articulo_enorme_se_devuelve_recortado() -> None:
    relleno = (LFT_59["texto"] + " ") * 400  # ~36 mil caracteres
    mcp_server.configurar(corpus=FakeCorpus([_art("513", relleno)]))
    try:
        error, [art] = _llamar("obtener_articulo", {"ley": "LFT", "numero": "513"})
    finally:
        mcp_server.configurar()
    assert not error
    assert art["recortado"] is True
    assert len(art["texto"]) == mcp_server.MAX_TEXTO_ARTICULO


def test_preguntar_responde_con_citas_y_usa_cache(entorno: dict) -> None:
    error, [resp] = _llamar("preguntar", {"pregunta": "¿Cuál es la jornada máxima?"})
    assert not error
    assert resp == {
        "respuesta": RESPUESTA.respuesta,
        "citas": ["[LFT, art. 59]"],
        "sin_evidencia": False,
    }
    # El LLM simulado ya gastó su guion: la segunda llamada solo puede salir de la caché.
    error, [otra] = _llamar("preguntar", {"pregunta": "cual es la jornada maxima"})
    assert not error
    assert otra == resp


def test_preguntar_respeta_el_tope_de_gasto(entorno: dict) -> None:
    entorno["guardia"].almacen.sumar_uso(1_000_000, 1_000_000, 3.0)  # por encima de 1 USD
    error, texto = _llamar("preguntar", {"pregunta": "¿Cuál es la jornada máxima?"})
    assert error
    assert "tope de consultas por hoy" in texto
