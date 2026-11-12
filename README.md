# ArticulIA

Agente que responde preguntas sobre leyes federales mexicanas citando el artículo exacto.
Si no encuentra evidencia en el corpus, lo dice en lugar de inventar.

> En desarrollo. Plan completo en [docs/PLAN.md](docs/PLAN.md).

## Desarrollo local

```bash
cp .env.example .env
docker compose up -d
uv sync
uv run pytest
```

## Ingesta

Descarga los PDFs de [LeyesBiblio](https://www.diputados.gob.mx/LeyesBiblio/index.htm) en `data/raw/` (CPEUM, LFT, CCF, LFPDPPP, LFDA, LFPC) y corre:

```bash
uv run python -m articulia.ingest
```

Genera `data/processed/<LEY>.jsonl` con un artículo por línea e imprime un resumen de validación.

Después indexa en PostgreSQL (texto completo + embeddings con `BAAI/bge-m3` en CPU; la primera vez
descarga los modelos, ~4.5 GB entre embeddings y reranker):

```bash
uv run python -m articulia.ingest.index
```

Es idempotente: solo recalcula embeddings de artículos cuyo contenido cambió.

## Limitaciones

No sustituye asesoría legal.
