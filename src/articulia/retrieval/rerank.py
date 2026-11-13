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


def _ordenar(modelo: object, query: str, candidates: list[Candidate]) -> list[Candidate]:
    # Lotes chicos: con lotes grandes todo se rellena al fragmento más largo y en CPU es
    # más del doble de lento (medido: 20.6 s con lote 32 contra 8.6 s con lote 4).
    scores = modelo.predict([(query, c.fragmento) for c in candidates], batch_size=4)  # type: ignore[attr-defined]
    for cand, s in zip(candidates, scores, strict=True):
        cand.score = float(s)
    return sorted(candidates, key=lambda c: c.score, reverse=True)


def rerank(query: str, candidates: list[Candidate], top_k: int = 5) -> list[Candidate]:
    """Reordena candidatos en cascada comparando la consulta con su mejor fragmento.

    Un cross-encoder ligero recorta los candidatos a `RERANK_PREFILTER_KEEP` y el principal
    (bge-reranker-v2-m3) reordena solo esos. En CPU baja de ~12 s a ~5 s por búsqueda con
    calidad equivalente (ver docs/decisiones.md).
    """
    from articulia.models import get_prefilter, get_reranker

    scored = [c for c in candidates if c.fragmento]
    if not scored:
        return []
    prefiltro = get_prefilter()
    keep = max(get_settings().rerank_prefilter_keep, top_k)
    if prefiltro is not None and len(scored) > keep:
        scored = _ordenar(prefiltro, query, scored)[:keep]
    return _ordenar(get_reranker(), query, scored)[:top_k]


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
