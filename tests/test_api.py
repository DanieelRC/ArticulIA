"""Pruebas de integración de la API con TestClient, LLM simulado y corpus en memoria."""

import json
from collections.abc import Iterator

import pytest
from fakes import LFT_59, LFT_61, FakeCorpus, FakeLLM, _tool_call
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from articulia.agent.graph import build_graph
from articulia.agent.state import Respuesta, Verificacion
from articulia.api.main import ServicioNoDisponible, app, get_corpus, get_graph
from articulia.api.schemas import MAX_PREGUNTA


class ApiCorpus(FakeCorpus):
    """Corpus en memoria con lo que además usa la API."""

    def __init__(self, articulos: list[dict], db_ok: bool = True) -> None:
        super().__init__(articulos)
        self.db_ok = db_ok

    def leyes(self) -> list[dict]:
        return [
            {
                "clave": "LFT",
                "nombre": "Ley Federal del Trabajo",
                "articulos": len(self.articulos),
                "fecha_ultima_reforma": "2026-05-14",
                "url": "https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf",
            }
        ]

    def obtener(self, ley: str, numero: str) -> dict | None:
        art = super().obtener(ley, numero)
        if art is None:
            return None
        return art | {"derogado": False, "fecha_ultima_reforma": "2026-05-14"}

    def ping(self) -> bool:
        return self.db_ok


RESPUESTA_OK = Respuesta(
    respuesta="La jornada ordinaria no puede pasar de cuarenta horas semanales [LFT, art. 59]."
)


def _llm_feliz() -> FakeLLM:
    return FakeLLM(
        razonar=[
            _tool_call("buscar_articulos", {"consulta": "jornada máxima"}),
            AIMessage("Listo"),
        ],
        respuestas=[RESPUESTA_OK],
        verificaciones=[Verificacion(respaldada=True)],
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    corpus = ApiCorpus([LFT_59, LFT_61])
    app.dependency_overrides[get_corpus] = lambda: corpus
    app.dependency_overrides[get_graph] = lambda: build_graph(_llm_feliz(), corpus)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _eventos(texto: str) -> list[tuple[str, dict]]:
    eventos = []
    for bloque in texto.strip().split("\n\n"):
        campos = dict(linea.split(": ", 1) for linea in bloque.splitlines() if ": " in linea)
        if "event" in campos:
            eventos.append((campos["event"], json.loads(campos["data"])))
    return eventos


# --- /ask -------------------------------------------------------------------------------------


def test_ask_devuelve_respuesta_con_citas(client: TestClient) -> None:
    r = client.post("/ask", json={"pregunta": "¿Cuántas horas puedo trabajar como máximo?"})
    assert r.status_code == 200
    body = r.json()
    assert body["sin_evidencia"] is False
    assert body["citas"] == [
        {
            "id": "LFT-59",
            "ley": "LFT",
            "numero": "59",
            "etiqueta": "[LFT, art. 59]",
            "url": "/articles/LFT/59",
        }
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"pregunta": ""},
        {"pregunta": "   "},
        {"pregunta": "x" * (MAX_PREGUNTA + 1)},
        {"pregunta": "¿Jornada máxima?", "leyes": ["LEY_ESTATAL"]},
    ],
)
def test_ask_valida_entrada(client: TestClient, payload: dict) -> None:
    r = client.post("/ask", json=payload)
    assert r.status_code == 422
    assert "detail" in r.json()


def test_ask_sin_api_key_responde_503() -> None:
    def sin_llm() -> None:
        raise ServicioNoDisponible("Falta la API key para LLM_PROVIDER=gemini en .env")

    app.dependency_overrides[get_graph] = sin_llm
    try:
        with TestClient(app) as c:
            r = c.post("/ask", json={"pregunta": "¿Jornada máxima?"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    assert "API key" in r.json()["detail"]


def test_error_inesperado_no_filtra_detalles() -> None:
    def roto() -> None:
        raise ZeroDivisionError("detalle interno")

    app.dependency_overrides[get_graph] = roto
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post("/ask", json={"pregunta": "¿Jornada máxima?"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 500
    assert "detalle interno" not in r.text


# --- /ask/stream ------------------------------------------------------------------------------


def test_stream_emite_pasos_y_respuesta(client: TestClient) -> None:
    with client.stream("POST", "/ask/stream", json={"pregunta": "¿Jornada máxima?"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        eventos = _eventos(r.read().decode("utf-8"))

    tipos = [t for t, _ in eventos]
    assert tipos[-1] == "respuesta"
    nodos = [d["nodo"] for t, d in eventos if t == "paso"]
    assert nodos == ["razonar", "herramientas", "razonar", "generar", "verificar"]
    herramientas = next(d for t, d in eventos if t == "paso" and d["nodo"] == "herramientas")
    assert set(herramientas["articulos"]) == {"LFT-59", "LFT-61"}
    assert eventos[-1][1]["citas"][0]["id"] == "LFT-59"


def test_stream_convierte_errores_en_evento() -> None:
    corpus = ApiCorpus([LFT_59])
    sin_guion = FakeLLM(razonar=[])  # el LLM simulado falla en la primera llamada
    app.dependency_overrides[get_graph] = lambda: build_graph(sin_guion, corpus)
    try:
        with TestClient(app) as c:
            r = c.post("/ask/stream", json={"pregunta": "¿Jornada máxima?"})
    finally:
        app.dependency_overrides.clear()
    assert _eventos(r.text) == [("error", {"detail": "Error al generar la respuesta."})]


# --- Corpus y salud ---------------------------------------------------------------------------


def test_laws(client: TestClient) -> None:
    r = client.get("/laws")
    assert r.status_code == 200
    assert r.json()[0]["clave"] == "LFT"


def test_article(client: TestClient) -> None:
    r = client.get("/articles/LFT/61")
    assert r.status_code == 200
    assert r.json()["texto"].startswith("La duración de la jornada diaria")


def test_article_inexistente_404(client: TestClient) -> None:
    r = client.get("/articles/LFT/9999")
    assert r.status_code == 404
    assert "9999" in r.json()["detail"]


def test_article_ley_desconocida_422(client: TestClient) -> None:
    assert client.get("/articles/LEYX/1").status_code == 422


def test_health_ok(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok", "db": True}


def test_health_sin_base_503() -> None:
    app.dependency_overrides[get_corpus] = lambda: ApiCorpus([], db_ok=False)
    try:
        with TestClient(app) as c:
            r = c.get("/health")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503
    assert r.json()["db"] is False


def test_openapi_documenta_los_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/ask", "/ask/stream", "/laws", "/articles/{ley}/{numero}", "/health"} <= set(paths)
