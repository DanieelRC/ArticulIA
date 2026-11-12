"""Prueba de punta a punta con el LLM real y la base indexada.

Se salta si no hay API key del proveedor configurado o si la base no está indexada. Cuesta
algunas llamadas al LLM, así que no corre en CI (Fase 7 usa la evaluación rápida).
"""

import pytest

from articulia.config import get_settings


def _requisitos() -> str | None:
    s = get_settings()
    key = {"gemini": s.google_api_key, "anthropic": s.anthropic_api_key, "xai": s.xai_api_key}
    if key[s.llm_provider] is None or not key[s.llm_provider].get_secret_value():
        return f"Sin API key para LLM_PROVIDER={s.llm_provider}"
    try:
        from articulia.db import connect

        with connect() as conn:
            if not conn.execute("SELECT EXISTS (SELECT 1 FROM chunks)").fetchone()[0]:
                return "Corpus sin indexar"
    except Exception as exc:
        return f"Base no disponible: {exc}"
    return None


motivo = _requisitos()
pytestmark = pytest.mark.skipif(motivo is not None, reason=motivo or "")


@pytest.fixture(scope="module")
def graph():  # noqa: ANN201
    from articulia.agent.graph import build_graph

    return build_graph()


def test_responde_con_citas_validas(graph) -> None:  # noqa: ANN001
    from articulia.agent.graph import responder

    pregunta = "¿Cuántos días de vacaciones me tocan en mi primer año de trabajo?"
    resp = responder(pregunta, graph=graph)
    assert not resp.sin_evidencia
    assert "LFT-76" in [c.article_id for c in resp.citas]


def test_se_abstiene_con_ley_estatal(graph) -> None:  # noqa: ANN001
    from articulia.agent.graph import responder

    resp = responder(
        "¿Cuánto cuesta la verificación vehicular según el reglamento de tránsito de la CDMX?",
        graph=graph,
    )
    assert resp.sin_evidencia
