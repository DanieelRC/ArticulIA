"""Pruebas de chunking, RRF y búsqueda. Las de búsqueda requieren la base indexada."""

import time
from collections.abc import Iterator
from datetime import date

import psycopg
import pytest

from articulia.ingest.index import CHUNK_CHARS, chunk_article, content_hash
from articulia.ingest.splitter import Article
from articulia.retrieval.hybrid import reciprocal_rank_fusion

# --- Unitarias --------------------------------------------------------------------------------


def _article(texto: str, **kw: object) -> Article:
    base = {
        "id": "LFT-61",
        "ley": "LFT",
        "ley_nombre": "Ley Federal del Trabajo",
        "numero": "61",
        "numero_base": 61,
        "tipo": "articulo",
        "derogado": False,
        "capitulo": "Capítulo II. Jornada de trabajo",
        "texto": texto,
        "reformas": [],
        "fecha_ultima_reforma": date(2026, 5, 14),
        "url": "https://www.diputados.gob.mx/LeyesBiblio/pdf/LFT.pdf",
    }
    return Article(**(base | kw))


LFT_61 = (
    "La duración de la jornada diaria será de ocho horas la diurna, siete la nocturna y siete\n"
    "horas y media la mixta."
)


def test_fragmento_lleva_encabezado_de_ley_articulo_y_capitulo() -> None:
    [chunk] = chunk_article(_article(LFT_61))
    header = "Ley Federal del Trabajo, artículo 61. Capítulo II. Jornada de trabajo\n"
    assert chunk.startswith(header)
    assert chunk.endswith("horas y media la mixta.")


def test_articulo_largo_se_parte_por_parrafos_sin_exceder_el_limite() -> None:
    texto = "\n\n".join([LFT_61] * 40)  # ~4.4k caracteres
    chunks = chunk_article(_article(texto))
    header = "Ley Federal del Trabajo, artículo 61. Capítulo II. Jornada de trabajo\n"
    assert len(chunks) > 1
    assert all(len(c) - len(header) <= CHUNK_CHARS for c in chunks)
    # No se pierde ni se duplica texto.
    assert sum(c.count("horas y media la mixta.") for c in chunks) == 40


def test_linea_gigante_se_parte_por_tamano() -> None:
    chunks = chunk_article(_article("x" * (CHUNK_CHARS * 2 + 10)), limit=CHUNK_CHARS)
    assert len(chunks) == 3


def test_hash_cambia_solo_si_cambia_el_contenido() -> None:
    assert content_hash(_article(LFT_61)) == content_hash(_article(LFT_61))
    assert content_hash(_article(LFT_61)) != content_hash(_article(LFT_61 + " "))


def test_rrf_premia_aparecer_en_ambas_listas() -> None:
    fused = reciprocal_rank_fusion({"vector": ["A", "B", "C"], "texto": ["C", "D", "A"]}, k=60)
    assert [c.article_id for c in fused][:2] == ["A", "C"]
    assert fused[0].ranks == {"vector": 1, "texto": 3}
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 63)


def test_rrf_con_una_lista_vacia_conserva_el_orden_de_la_otra() -> None:
    fused = reciprocal_rank_fusion({"vector": ["A", "B"], "texto": []})
    assert [c.article_id for c in fused] == ["A", "B"]


# --- Integración (base indexada) --------------------------------------------------------------


@pytest.fixture(scope="module")
def conn() -> Iterator[psycopg.Connection]:
    from articulia.db import connect

    try:
        c = connect()
        indexed = c.execute(
            "SELECT to_regclass('chunks') IS NOT NULL AND EXISTS (SELECT 1 FROM chunks)"
        ).fetchone()[0]
    except psycopg.Error:
        pytest.skip("PostgreSQL no disponible; corre `docker compose up -d`")
    if not indexed:
        c.close()
        pytest.skip("Corpus sin indexar; corre `uv run python -m articulia.ingest.index`")
    yield c
    c.close()


def test_jornada_maxima_devuelve_lft_61(conn: psycopg.Connection) -> None:
    from articulia.retrieval.rerank import search

    ids = [r.id for r in search(conn, "jornada máxima de trabajo", top_k=5, use_reranker=True)]
    assert "LFT-61" in ids  # duración de la jornada diaria
    assert "LFT-59" in ids  # máximo semanal (reforma de 2026)


def test_filtro_por_ley(conn: psycopg.Connection) -> None:
    from articulia.retrieval.rerank import search

    results = search(
        conn, "derecho a la protección de datos personales", leyes=["CPEUM"], use_reranker=False
    )
    assert results
    assert {r.ley for r in results} == {"CPEUM"}


def test_busqueda_hibrida_en_menos_de_un_segundo(conn: psycopg.Connection) -> None:
    from articulia.retrieval.rerank import search

    search(conn, "calentamiento", top_k=5, use_reranker=False)  # carga del modelo
    start = time.perf_counter()
    pregunta = "¿cuántos días de vacaciones me tocan el primer año?"
    results = search(conn, pregunta, use_reranker=False)
    assert time.perf_counter() - start < 1.0
    assert "LFT-76" in [r.id for r in results]
