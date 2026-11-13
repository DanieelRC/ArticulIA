"""Búsqueda híbrida: vectorial (pgvector) + texto completo (tsvector), fusionadas con RRF."""

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import psycopg

from articulia.config import get_settings

CANDIDATES = 50  # resultados que aporta cada búsqueda antes de fusionar


@dataclass
class Candidate:
    """Artículo candidato con su procedencia y el fragmento más parecido a la consulta."""

    article_id: str
    score: float = 0.0
    ranks: dict[str, int] = field(default_factory=dict)  # {"vector": 1, "texto": 3}
    fragmento: str | None = None


def reciprocal_rank_fusion(
    rankings: dict[str, Sequence[str]], k: int = 60, weights: dict[str, float] | None = None
) -> list[Candidate]:
    """Fusiona listas ordenadas: score(d) = Σ w_i / (k + rango_i(d)), con rangos desde 1.

    Solo usa posiciones, no puntajes, así que no hay que calibrar la distancia coseno contra
    el puntaje de `ts_rank`, que viven en escalas distintas. Sin `weights`, todas pesan 1.
    """
    weights = weights or {}
    fused: dict[str, Candidate] = {}
    for source, ids in rankings.items():
        w = weights.get(source, 1.0)
        for rank, article_id in enumerate(ids, start=1):
            cand = fused.setdefault(article_id, Candidate(article_id))
            cand.score += w / (k + rank)
            cand.ranks[source] = rank
    return sorted(fused.values(), key=lambda c: c.score, reverse=True)


_VECTOR_SQL = """
SELECT article_id, min(distancia) AS d
FROM (
    SELECT article_id, embedding <=> %(q)s AS distancia
    FROM chunks
    WHERE %(leyes)s::text[] IS NULL OR ley = ANY(%(leyes)s)
    ORDER BY embedding <=> %(q)s
    LIMIT %(fetch)s
) cercanos
GROUP BY article_id
ORDER BY d
LIMIT %(limit)s
"""

# plainto_tsquery une los términos con AND; una pregunta en lenguaje natural casi nunca contiene
# todas sus palabras en un mismo artículo, así que se cambian a OR y ts_rank premia a los que
# contienen más. La normalización 1 divide entre log(longitud) para no favorecer artículos enormes.
_TEXT_SQL = """
WITH q AS (
    SELECT to_tsquery('es', replace(plainto_tsquery('es', %(texto)s)::text, '&', '|')) AS query
)
SELECT id
FROM articles, q
WHERE tsv @@ q.query
  AND NOT derogado
  AND (%(leyes)s::text[] IS NULL OR ley = ANY(%(leyes)s))
ORDER BY ts_rank(tsv, q.query, 1) DESC
LIMIT %(limit)s
"""

_BEST_CHUNK_SQL = """
SELECT DISTINCT ON (article_id) article_id, texto
FROM chunks
WHERE article_id = ANY(%(ids)s)
ORDER BY article_id, embedding <=> %(q)s
"""


def vector_search(
    conn: psycopg.Connection,
    query_vec: np.ndarray,
    leyes: list[str] | None = None,
    limit: int = CANDIDATES,
) -> list[str]:
    """Ids de artículo ordenados por la distancia coseno de su fragmento más cercano."""
    # Con filtro por ley, el escaneo iterativo de pgvector sigue buscando en el índice HNSW
    # hasta juntar suficientes filas que pasen el WHERE.
    conn.execute("SET hnsw.iterative_scan = relaxed_order")
    conn.execute("SET hnsw.ef_search = 200")
    rows = conn.execute(
        _VECTOR_SQL, {"q": query_vec, "leyes": leyes, "fetch": limit * 4, "limit": limit}
    ).fetchall()
    return [r[0] for r in rows]


def text_search(
    conn: psycopg.Connection, query: str, leyes: list[str] | None = None, limit: int = CANDIDATES
) -> list[str]:
    """Ids de artículo ordenados por relevancia de texto completo en español."""
    rows = conn.execute(_TEXT_SQL, {"texto": query, "leyes": leyes, "limit": limit}).fetchall()
    return [r[0] for r in rows]


def hybrid_search(
    conn: psycopg.Connection,
    query: str,
    leyes: list[str] | None = None,
    limit: int = 20,
    query_vec: np.ndarray | None = None,
) -> list[Candidate]:
    """Corre ambas búsquedas, las fusiona con RRF y adjunta el fragmento más relevante."""
    if query_vec is None:
        from articulia.models import embed

        query_vec = embed([query])[0]
    fused = reciprocal_rank_fusion(
        {
            "vector": vector_search(conn, query_vec, leyes),
            "texto": text_search(conn, query, leyes),
        },
        k=get_settings().rrf_k,
        weights={"texto": get_settings().rrf_text_weight},
    )[:limit]
    best = dict(
        conn.execute(
            _BEST_CHUNK_SQL, {"ids": [c.article_id for c in fused], "q": query_vec}
        ).fetchall()
    )
    for cand in fused:
        cand.fragmento = best.get(cand.article_id)
    return fused
