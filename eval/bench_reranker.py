"""Compara rerankers sobre el dataset: calidad (hit@5, MRR) contra latencia en CPU.

Uso: uv run python eval/bench_reranker.py

Los candidatos de la búsqueda híbrida se calculan una sola vez por pregunta; cada configuración
solo reordena, así la comparación mide únicamente al reranker.
"""

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

from articulia.evaluation import (  # noqa: E402
    cargar_dataset,
    hit_at_k,
    media,
    percentil,
    reciprocal_rank,
)

RAIZ = Path(__file__).resolve().parent.parent
V2_M3 = "BAAI/bge-reranker-v2-m3"

# (etiqueta, modelo, candidatos, max_length, cuantizado int8)
CONFIGS = [
    ("v2-m3 · 20 cand · 512 tok (actual)", V2_M3, 20, 512, False),
    ("v2-m3 · 20 cand · 256 tok", V2_M3, 20, 256, False),
    ("v2-m3 · 12 cand · 256 tok", V2_M3, 12, 256, False),
    ("v2-m3 int8 · 20 cand · 256 tok", V2_M3, 20, 256, True),
    ("bge-reranker-base · 20 cand · 256 tok", "BAAI/bge-reranker-base", 20, 256, False),
    ("bge-reranker-base int8 · 20 cand · 256 tok", "BAAI/bge-reranker-base", 20, 256, True),
    (
        "mMiniLM-L12 mmarco · 20 cand · 256 tok",
        "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        20,
        256,
        False,
    ),
]


def cargar(modelo: str, max_length: int, int8: bool):  # noqa: ANN201
    """Crea el cross-encoder; con `int8`, cuantiza dinámicamente las capas lineales."""
    import torch
    from sentence_transformers import CrossEncoder

    ce = CrossEncoder(modelo, max_length=max_length, device="cpu")
    if int8:
        ce.model = torch.quantization.quantize_dynamic(
            ce.model, {torch.nn.Linear}, dtype=torch.qint8
        )
    return ce


def main() -> None:
    """Imprime una tabla Markdown con calidad y latencia por configuración."""
    from articulia.db import connect
    from articulia.retrieval.hybrid import hybrid_search

    preguntas = [
        p for p in cargar_dataset(RAIZ / "eval" / "dataset.jsonl") if p.tipo != "sin_respuesta"
    ]
    with connect() as conn:
        pools = {p.id: hybrid_search(conn, p.pregunta, limit=20) for p in preguntas}
    en_pool = media(
        [float(any(c.article_id in p.esperados for c in pools[p.id])) for p in preguntas]
    )
    print(f"Artículo esperado entre los 20 candidatos: {en_pool:.2f}", file=sys.stderr)

    filas = []
    cache: dict[tuple, object] = {}
    for etiqueta, modelo, n, max_len, int8 in CONFIGS:
        clave = (modelo, max_len, int8)
        if clave not in cache:
            cache[clave] = cargar(modelo, max_len, int8)
        ce = cache[clave]
        ce.predict([("calentamiento", "texto")])
        hits, rrs, tiempos = [], [], []
        for p in preguntas:
            cands = [c for c in pools[p.id][:n] if c.fragmento]
            t0 = time.perf_counter()
            scores = ce.predict([(p.pregunta, c.fragmento) for c in cands], batch_size=4)
            tiempos.append(time.perf_counter() - t0)
            orden = [
                c.article_id
                for _, c in sorted(zip(scores, cands, strict=True), key=lambda x: -x[0])
            ]
            hits.append(hit_at_k(orden, p.esperados))
            rrs.append(reciprocal_rank(orden, p.esperados))
        fila = (etiqueta, media(hits), media(rrs), percentil(tiempos, 50), percentil(tiempos, 95))
        filas.append(fila)
        print("| {} | {:.2f} | {:.2f} | {:.1f} s | {:.1f} s |".format(*fila), file=sys.stderr)

    print("| Reranker | Hit@5 | MRR | Latencia p50 | Latencia p95 |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for f in filas:
        print("| {} | {:.2f} | {:.2f} | {:.1f} s | {:.1f} s |".format(*f))


if __name__ == "__main__":
    main()
