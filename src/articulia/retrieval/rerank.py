"""Reordenamiento con cross-encoder y búsqueda completa (híbrida + rerank)."""

from datetime import date

import psycopg
from pydantic import BaseModel

from articulia.config import get_settings
from articulia.retrieval.hybrid import Candidate, hybrid_search


class SearchResult(BaseModel):
    """Artículo recuperado, listo para citarse."""

    id: str
    ley: str
    ley_nombre: str
    numero: str
    tipo: str
    titulo: str | None
    capitulo: str | None
    texto: str
    fragmento: str
    url: str
    fecha_ultima_reforma: date | None
    score: float


def rerank(query: str, candidates: list[Candidate], top_k: int = 5) -> list[Candidate]:
    """Reordena candidatos con bge-reranker-v2-m3 comparando la consulta con su mejor fragmento."""
    from articulia.models import get_reranker

    scored = [c for c in candidates if c.fragmento]
    if not scored:
        return []
    # Lotes chicos: con lotes grandes todo se rellena al fragmento más largo y en CPU es
    # más del doble de lento (medido: 20.6 s con lote 32 contra 8.6 s con lote 4).
    scores = get_reranker().predict([(query, c.fragmento) for c in scored], batch_size=4)
    for cand, s in zip(scored, scores, strict=True):
        cand.score = float(s)
    return sorted(scored, key=lambda c: c.score, reverse=True)[:top_k]


_ARTICLES_SQL = """
SELECT id, ley, ley_nombre, numero, tipo, titulo, capitulo, texto, url, fecha_ultima_reforma
FROM articles WHERE id = ANY(%s)
"""


def search(
    conn: psycopg.Connection,
    query: str,
    leyes: list[str] | None = None,
    top_k: int = 5,
    use_reranker: bool | None = None,
) -> list[SearchResult]:
    """Búsqueda completa: híbrida (RRF) sobre todo el corpus, reranking de los mejores y top-k.

    `use_reranker=None` usa `RERANKER_ENABLED` de la configuración.
    """
    settings = get_settings()
    if use_reranker is None:
        use_reranker = settings.reranker_enabled
    candidates = hybrid_search(conn, query, leyes, limit=settings.rerank_candidates)
    ranked = rerank(query, candidates, top_k) if use_reranker else candidates[:top_k]
    cols = ("id", "ley", "ley_nombre", "numero", "tipo", "titulo", "capitulo", "texto", "url",
            "fecha_ultima_reforma")  # fmt: skip
    rows = {
        r[0]: dict(zip(cols, r, strict=True))
        for r in conn.execute(_ARTICLES_SQL, ([c.article_id for c in ranked],))
    }
    return [
        SearchResult(**rows[c.article_id], fragmento=c.fragmento or "", score=c.score)
        for c in ranked
    ]
