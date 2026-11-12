"""Indexa los JSONL de data/processed en PostgreSQL (texto completo + embeddings).

Uso: `uv run python -m articulia.ingest.index [data/processed]`

Es idempotente: un artículo cuyo contenido no cambió conserva sus embeddings, y los artículos
que ya no están en el corpus se borran.
"""

import hashlib
import sys
import time
from pathlib import Path

import psycopg

from articulia.db import apply_schema, connect
from articulia.ingest.splitter import Article

CHUNK_CHARS = 1500  # ~400 tokens de bge-m3 en español, por debajo del límite de 512


def load_articles(processed_dir: Path) -> list[Article]:
    """Lee todos los `<LEY>.jsonl` del directorio."""
    articles: list[Article] = []
    for path in sorted(processed_dir.glob("*.jsonl")):
        with open(path, encoding="utf-8") as f:
            articles.extend(Article.model_validate_json(line) for line in f if line.strip())
    return articles


def content_hash(article: Article) -> str:
    """Huella del contenido que afecta a los embeddings."""
    return hashlib.sha256(article.model_dump_json().encode("utf-8")).hexdigest()


def chunk_header(article: Article) -> str:
    """Contexto que se antepone a cada fragmento: ley, artículo y capítulo."""
    tipo = "artículo transitorio" if article.tipo == "transitorio" else "artículo"
    parts = [f"{article.ley_nombre}, {tipo} {article.numero}"]
    if article.capitulo:
        parts.append(article.capitulo)
    elif article.titulo:
        parts.append(article.titulo)
    return ". ".join(parts) + "\n"


def _pieces(texto: str, limit: int) -> list[str]:
    """Párrafos; los que exceden el límite se parten por línea y, si aún exceden, por tamaño."""
    out: list[str] = []
    for para in texto.split("\n\n"):
        if len(para) <= limit:
            out.append(para)
            continue
        for line in para.split("\n"):
            out.extend(line[i : i + limit] for i in range(0, len(line), limit))
    return [p for p in out if p.strip()]


def chunk_article(article: Article, limit: int = CHUNK_CHARS) -> list[str]:
    """Divide el texto en fragmentos de hasta `limit` caracteres sin partir párrafos si es posible.

    Cada fragmento lleva el encabezado de `chunk_header` para que el embedding sepa de qué
    ley y artículo viene aunque el fragmento sea una fracción suelta.
    """
    header = chunk_header(article)
    chunks: list[str] = []
    current = ""
    for piece in _pieces(article.texto, limit):
        if current and len(current) + len(piece) + 2 > limit:
            chunks.append(current)
            current = piece
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return [header + c for c in chunks]


_UPSERT = """
INSERT INTO articles (id, ley, ley_nombre, numero, numero_base, tipo, derogado, libro, titulo,
    capitulo, seccion, texto, reformas, fecha_ultima_reforma, url, content_hash)
VALUES (%(id)s, %(ley)s, %(ley_nombre)s, %(numero)s, %(numero_base)s, %(tipo)s, %(derogado)s,
    %(libro)s, %(titulo)s, %(capitulo)s, %(seccion)s, %(texto)s, %(reformas)s,
    %(fecha_ultima_reforma)s, %(url)s, %(content_hash)s)
ON CONFLICT (id) DO UPDATE SET
    ley = EXCLUDED.ley, ley_nombre = EXCLUDED.ley_nombre, numero = EXCLUDED.numero,
    numero_base = EXCLUDED.numero_base, tipo = EXCLUDED.tipo, derogado = EXCLUDED.derogado,
    libro = EXCLUDED.libro, titulo = EXCLUDED.titulo, capitulo = EXCLUDED.capitulo,
    seccion = EXCLUDED.seccion, texto = EXCLUDED.texto, reformas = EXCLUDED.reformas,
    fecha_ultima_reforma = EXCLUDED.fecha_ultima_reforma, url = EXCLUDED.url,
    content_hash = EXCLUDED.content_hash
"""


def index_articles(conn: psycopg.Connection, articles: list[Article]) -> dict[str, int]:
    """Inserta o actualiza artículos y recalcula embeddings solo donde cambió el contenido.

    Los artículos derogados se guardan (para `obtener_articulo`) pero no se fragmentan:
    su texto es "Se deroga." y solo metería ruido en la búsqueda vectorial.
    """
    from articulia.models import embed  # importa torch solo si hace falta

    hashes = {a.id: content_hash(a) for a in articles}
    stored = dict(conn.execute("SELECT id, content_hash FROM articles").fetchall())
    with_chunks = {r[0] for r in conn.execute("SELECT DISTINCT article_id FROM chunks")}

    removed = [i for i in stored if i not in hashes]
    if removed:
        conn.execute("DELETE FROM articles WHERE id = ANY(%s)", (removed,))

    changed = [a for a in articles if stored.get(a.id) != hashes[a.id]]
    with conn.cursor() as cur:
        cur.executemany(_UPSERT, [a.model_dump() | {"content_hash": hashes[a.id]} for a in changed])

    changed_ids = {a.id for a in changed}
    to_embed = [
        a for a in articles if not a.derogado and (a.id in changed_ids or a.id not in with_chunks)
    ]
    rows: list[tuple[str, int, str, str]] = [
        (a.id, i, a.ley, text) for a in to_embed for i, text in enumerate(chunk_article(a))
    ]
    stale = list(changed_ids | {a.id for a in to_embed})
    conn.execute("DELETE FROM chunks WHERE article_id = ANY(%s)", (stale,))
    if rows:
        vectors = embed([r[3] for r in rows])
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (article_id, idx, ley, texto, embedding) "
                "VALUES (%s, %s, %s, %s, %s)",
                [(*r, v) for r, v in zip(rows, vectors, strict=True)],
            )
    conn.commit()
    return {
        "articulos": len(articles),
        "actualizados": len(changed),
        "borrados": len(removed),
        "fragmentos_nuevos": len(rows),
    }


def main(processed_dir: Path) -> None:
    """Aplica el esquema e indexa el corpus."""
    articles = load_articles(processed_dir)
    if not articles:
        sys.exit(f"No hay JSONL en {processed_dir}; corre `python -m articulia.ingest` primero.")
    start = time.perf_counter()
    with connect() as conn:
        apply_schema(conn)
        stats = index_articles(conn, articles)
    print(stats, f"{time.perf_counter() - start:.1f}s")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/processed"))
