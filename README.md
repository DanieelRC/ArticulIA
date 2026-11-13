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

`pregunta` es obligatoria (3 a 500 caracteres); `leyes` es opcional (`CPEUM`, `LFT`, `CCF`,
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
- `event: token` con cada fragmento de la respuesta mientras se escribe: `{"texto": "Las personas "}`
- `event: borrador_descartado` si el verificador rechaza lo escrito (hay que limpiar el texto parcial)
- `event: respuesta` al final, ya verificada, con el mismo JSON que `/ask`
- `event: error` si algo falla después de empezar el stream

```bash
curl -N -X POST localhost:8000/ask/stream -H "Content-Type: application/json" \
  -d '{"pregunta": "¿Cuántas horas dura la jornada diurna?"}'
```

**Errores:** 422 si la entrada no es válida, 404 si el artículo no existe, 429 si se alcanzó el
límite por IP o el tope de gasto diario (con `Retry-After`), 503 si falta la API key, la base no
responde o hay demasiadas consultas en curso, 500 con un mensaje genérico (el detalle queda en
los logs).

### Control de gasto

Cada pregunta cuesta dinero en el proveedor del LLM. La API lo acota con un tope de gasto diario,
límite por IP, caché de respuestas, topes de tokens y cupo de concurrencia; todo se configura por
variables de entorno (ver `.env.example`) y se explica en [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md).

## Interfaz web

Con `docker compose up -d --build` queda en http://localhost:3000 (nginx sirve la interfaz y
redirige `/api` a FastAPI). Para desarrollarla con recarga en caliente:

```bash
cd frontend
npm install
npm run dev
```

Abre http://localhost:5173; Vite redirige `/api` a `localhost:8000`. Pruebas: `npm test`.

- **Portada** (`/`): qué hace, cómo funciona, el corpus y las métricas reales de la evaluación.
- **Consulta** (`/consulta`): la respuesta se escribe en vivo; al pasar la verificación recibe el
  sello «Cotejado». Cada cita abre el texto completo del artículo, con navegación al artículo
  vecino y enlace al PDF oficial.
- **Archivo**: las consultas se guardan en el navegador y se pueden reabrir o borrar.
- Filtro por ley; sin selección busca en todo el corpus.

La dirección visual está documentada en [DESIGN.md](DESIGN.md). Para mostrar el enlace al
repositorio en la portada, define `VITE_GITHUB_URL` al compilar la interfaz.

## Despliegue

Guía completa para un VPS con HTTPS en [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Evaluación

`eval/dataset.jsonl` tiene las preguntas (formato en [docs/decisiones.md](docs/decisiones.md)).

```bash
uv run python eval/run_eval.py --solo-recuperacion   # hit@5 y MRR, sin LLM
uv run python eval/run_eval.py                       # completa, con agente y Ragas
```

Imprime una tabla Markdown y guarda el detalle por pregunta en `eval/results/`.
Con `LANGSMITH_TRACING=true` y `LANGSMITH_API_KEY` cada consulta queda trazada en LangSmith.

## Limitaciones

No sustituye asesoría legal.
