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

## API

Con la base indexada y una API key en `.env` (`GOOGLE_API_KEY` si `LLM_PROVIDER=gemini`):

```bash
docker compose up -d --build
```

O sin Docker para la API: `uv run uvicorn articulia.api.main:app --reload`.
Documentación interactiva (OpenAPI) en http://localhost:8000/docs.

| Método | Ruta | Qué hace |
| --- | --- | --- |
| `POST` | `/ask` | Responde una pregunta con citas verificadas |
| `POST` | `/ask/stream` | Igual que `/ask`, pero emite cada paso del agente por SSE |
| `GET` | `/laws` | Leyes del corpus, número de artículos y fecha de última reforma |
| `GET` | `/articles/{ley}/{numero}` | Texto completo de un artículo (`/articles/LFT/61`) |
| `GET` | `/health` | Estado del servicio y de la base (503 si la base no responde) |

**`POST /ask`**

```json
{ "pregunta": "¿Cuántos días de vacaciones me tocan en mi primer año?", "leyes": ["LFT"] }
```

`pregunta` es obligatoria (3 a 1000 caracteres); `leyes` es opcional (`CPEUM`, `LFT`, `CCF`,
`LFPDPPP`, `LFDA`, `LFPC`). Respuesta:

```json
{
  "respuesta": "… [LFT, art. 76].",
  "citas": [{ "id": "LFT-76", "ley": "LFT", "numero": "76",
              "etiqueta": "[LFT, art. 76]", "url": "/articles/LFT/76" }],
  "sin_evidencia": false
}
```

Si no hay evidencia en el corpus, `sin_evidencia` es `true` y `citas` va vacía.

**`POST /ask/stream`** (Server-Sent Events). Mismo cuerpo que `/ask`. Emite:

- `event: paso` por cada nodo del agente: `{"nodo": "herramientas", "mensaje": "5 artículos recuperados", "articulos": ["LFT-76", …]}`
- `event: respuesta` al final, con el mismo JSON que `/ask`
- `event: error` si algo falla después de empezar el stream

```bash
curl -N -X POST localhost:8000/ask/stream -H "Content-Type: application/json" \
  -d '{"pregunta": "¿Cuántas horas dura la jornada diurna?"}'
```

**Errores:** 422 si la entrada no es válida, 404 si el artículo no existe, 503 si falta la API key
del LLM o la base no responde, 500 con un mensaje genérico (el detalle queda en los logs).

## Interfaz web

Con `docker compose up -d --build` queda en http://localhost:3000 (nginx sirve la interfaz y
redirige `/api` a FastAPI). Para desarrollarla con recarga en caliente:

```bash
cd frontend
npm install
npm run dev
```

Abre http://localhost:5173; Vite redirige `/api` a `localhost:8000`. Pruebas: `npm test`.

- Muestra los pasos del agente mientras trabaja (`/ask/stream`).
- Cada cita `[LFT, art. 61]` es un botón que abre el texto completo del artículo en un panel lateral,
  con su ubicación en la ley, historial de reformas y enlace al PDF oficial.
- Filtro por ley; sin selección busca en todo el corpus.

## Limitaciones

No sustituye asesoría legal.
