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

## Limitaciones

No sustituye asesoría legal.
