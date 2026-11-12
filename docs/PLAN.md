# ArticulIA — Guía de desarrollo paso a paso

Nov 11, 2026 · @Daniel Rodríguez Carreón

## Resumen

ArticulIA es un agente que responde preguntas sobre leyes federales mexicanas y cita el artículo exacto en el que se basa cada afirmación. Si no encuentra evidencia en el corpus, lo dice en lugar de inventar. El objetivo es un proyecto de portafolio que cubra en un solo repositorio lo que más piden las vacantes de IA junior en CDMX, que es LangGraph, LangChain, FastAPI, Docker, evaluación de RAG, observabilidad, CI/CD y MCP.

La duración objetivo es de tres semanas. Desde el final de la segunda ya es presentable en el CV.

### Cómo usar esta guía con Claude Code

1. Exporta este documento a Markdown y guárdalo en el repositorio como `docs/PLAN.md`.
2. En la Fase 0 se crea un `CLAUDE.md` con las reglas del proyecto. Claude Code lo lee en cada sesión.
3. Trabaja una fase a la vez con el prompt sugerido. No le pidas el proyecto completo en un solo mensaje, porque el resultado es más difícil de revisar y de defender en una entrevista.
4. Al cerrar cada fase, verifica su criterio de terminado, corre las pruebas y haz un commit.
5. Pide a Claude Code que te explique cada decisión no obvia y anótala en `docs/decisiones.md`. En las entrevistas te van a preguntar por qué elegiste cada pieza, y esas notas son tu respaldo.

Una regla para que el proyecto sea realmente tuyo es escribir tú mismo las pruebas del divisor por artículo (Fase 1) y el dataset de evaluación (Fase 6). Son las dos partes donde más se nota el criterio propio.

## Stack y arquitectura

Todo corre localmente con Docker Compose y sin costo, salvo las llamadas al LLM. El proveedor del LLM se elige por variable de entorno, así puedes usar Gemini con su capa gratuita durante el desarrollo y cambiar a Claude o Grok sin tocar código.

| Capa | Tecnología | Por qué |
| --- | --- | --- |
| Lenguaje y dependencias | Python 3.12 con `uv` | Instalación rápida y lockfile reproducible |
| Ingesta | LangChain (loaders), PyMuPDF y un divisor propio por artículo | El corte por artículo es la base de citas precisas |
| Embeddings | `BAAI/bge-m3` con sentence-transformers, en local | Multilingüe, buen español, sin costo por llamada |
| Base de datos | PostgreSQL 16 con pgvector y búsqueda de texto completo en español | Ya lo dominas y permite búsqueda híbrida en una sola base |
| Reranker | `BAAI/bge-reranker-v2-m3` | Mejora el orden de los resultados antes de generar |
| Agente | LangGraph | Grafo con estado, herramientas, límite de iteraciones y verificación |
| LLM | Gemini, Claude o Grok vía LangChain, configurable | Sin dependencia de un solo proveedor |
| API | FastAPI, Pydantic y streaming por SSE | El framework que piden casi todas las vacantes |
| Frontend | React, Vite y TypeScript | Tu fuerte, para que la demo se vea bien |
| Observabilidad | LangSmith | Trazas, latencia y costo por consulta |
| Evaluación | Ragas y pytest | Métricas de RAG reproducibles |
| Infraestructura | Docker Compose | Un solo comando para levantar todo |
| CI | GitHub Actions | Lint, pruebas y evaluación rápida en cada push |
| Integración | Servidor MCP con el SDK oficial de Python | Expone las herramientas del agente a cualquier cliente MCP |

&#91;embedded content: arquitectura de ArticulIA · ingesta, agente y clientes\]

La web y el servidor MCP llaman al mismo agente, y el agente usa las mismas herramientas sobre una sola base. La ingesta corre una vez por actualización del corpus.

## Estructura del repositorio

El backend, el frontend, la evaluación y el servidor MCP viven en el mismo repositorio y comparten el paquete `articulia`, de modo que las herramientas se escriben una sola vez.

```text
articulia/
├── CLAUDE.md                  # reglas del proyecto para Claude Code
├── README.md
├── docker-compose.yml
├── .env.example
├── pyproject.toml             # gestionado con uv
├── docs/
│   ├── PLAN.md                # esta guía
│   └── decisiones.md          # por qué se eligió cada pieza
├── data/
│   ├── raw/                   # PDFs descargados (en .gitignore)
│   └── processed/             # artículos en JSONL
├── src/articulia/
│   ├── config.py              # Pydantic Settings, lee .env
│   ├── db/                    # conexión, esquema y migraciones SQL
│   ├── ingest/
│   │   ├── loader.py          # PDF a texto limpio
│   │   ├── splitter.py        # divide por artículo y extrae metadatos
│   │   └── index.py           # embeddings e inserción en pgvector
│   ├── retrieval/
│   │   ├── hybrid.py          # vector + texto completo con RRF
│   │   └── rerank.py
│   ├── agent/
│   │   ├── state.py
│   │   ├── tools.py           # buscar, obtener_articulo, comparar
│   │   ├── nodes.py
│   │   └── graph.py
│   ├── api/
│   │   ├── main.py
│   │   └── schemas.py
│   └── mcp_server.py
├── frontend/                  # React + Vite + TypeScript
├── eval/
│   ├── dataset.jsonl          # preguntas con artículo esperado
│   ├── run_eval.py
│   └── results/
├── tests/
└── .github/workflows/ci.yml
```

## Fases de desarrollo

Son nueve fases en tres semanas, más dos opcionales. Cada una trae sus tareas, el prompt para Claude Code y el criterio que debe cumplirse antes de pasar a la siguiente.

| Semana | Fases | Resultado al cierre |
| --- | --- | --- |
| 1 | 0, 1, 2 | Corpus indexado y búsqueda híbrida funcionando |
| 2 | 3, 4, 5 | Agente con citas, API y frontend. Ya va al CV |
| 3 | 6, 7, 8 | Métricas publicadas, CI y servidor MCP |

### Fase 0. Preparación

1. Crea el repositorio `articulia` en GitHub y clónalo.
2. Inicializa el proyecto con `uv init` y agrega ruff, pytest y pre-commit.
3. Escribe `docker-compose.yml` con un servicio de PostgreSQL 16 que use la imagen `pgvector/pgvector`.
4. Crea `.env.example` con `LLM_PROVIDER`, `LLM_MODEL`, la API key, `DATABASE_URL` y las variables de LangSmith.
5. Crea `CLAUDE.md` con este contenido inicial.

```markdown
# ArticulIA
Agente que responde preguntas sobre leyes federales mexicanas citando el artículo exacto.
Plan completo en docs/PLAN.md. Trabaja solo la fase que se indique.

## Reglas
- Python 3.12, dependencias con uv. Formato y lint con ruff.
- Toda función pública lleva type hints y docstring breve.
- Cada módulo nuevo lleva pruebas en tests/.
- Nunca inventes artículos ni contenido legal en datos de prueba; usa texto real del corpus.
- Configuración solo por variables de entorno (src/articulia/config.py).
- Antes de terminar una tarea corre: uv run ruff check . && uv run pytest
- Anota decisiones no obvias en docs/decisiones.md.
```

**Prompt para Claude Code.** Lee docs/PLAN.md y CLAUDE.md. Ejecuta la Fase 0, crea la estructura de carpetas de la sección Estructura del repositorio con archivos vacíos donde haga falta, y deja Docker Compose levantando PostgreSQL con la extensión vector habilitada.

**Terminado cuando** `docker compose up -d` levanta la base, `CREATE EXTENSION vector` funciona y `uv run pytest` corre sin errores.

### Fase 1. Corpus e ingesta

1. Descarga a mano los PDFs vigentes desde la Biblioteca de Leyes Federales de la Cámara de Diputados (diputados.gob.mx/LeyesBiblio). Empieza con seis: Constitución Política, Ley Federal del Trabajo, Código Civil Federal, Ley Federal de Protección de Datos Personales en Posesión de los Particulares, Ley Federal del Derecho de Autor y Ley Federal de Protección al Consumidor.
2. Convierte cada PDF a texto limpio, quitando encabezados, pies de página y números de página repetidos.
3. Divide el texto por artículo con una expresión regular sobre `Artículo N.-` y sus variantes (`Artículo 5o.`, `Artículo 123 Bis`). Los artículos transitorios van aparte, marcados como tales.
4. Guarda cada artículo con sus metadatos (ley, número, título y capítulo si existen, fecha de última reforma, texto y URL de origen) en `data/processed/<ley>.jsonl`.
5. Escribe tú las pruebas del divisor con casos reales, incluidos artículos con fracciones, artículos Bis y artículos derogados.

**Prompt para Claude Code.** Implementa la Fase 1. Los PDFs ya están en data/raw. Empieza por loader.py y splitter.py; yo escribiré las pruebas del divisor, tú propón los casos borde que debería cubrir.

**Terminado cuando** cada ley tiene un JSONL, el número de artículos coincide con el de la ley (por ejemplo, la Constitución tiene 136 artículos permanentes) y las pruebas del divisor pasan.

### Fase 2. Indexación y búsqueda híbrida

1. Crea la tabla `articles` con columnas para metadatos, el texto, un `vector(1024)` para bge-m3 y un `tsvector` con configuración `spanish`.
2. Agrega índices HNSW sobre el vector y GIN sobre el tsvector.
3. Implementa `index.py`, que lee los JSONL, calcula embeddings por lotes e inserta. Debe ser idempotente.
4. Implementa `hybrid.py`, que corre la búsqueda vectorial y la de texto completo por separado y las fusiona con Reciprocal Rank Fusion.
5. Pasa los 20 mejores resultados por el reranker y devuelve los 5 primeros.
6. Agrega filtros opcionales por ley.

**Prompt para Claude Code.** Implementa la Fase 2. Explícame en docs/decisiones.md por qué RRF y qué valor de k usas. Agrega una prueba que verifique que la consulta 'jornada máxima de trabajo' devuelve el artículo 61 de la Ley Federal del Trabajo entre los primeros cinco.

**Terminado cuando** la búsqueda devuelve artículos relevantes en menos de un segundo y la prueba de la jornada pasa.

### Fase 3. Agente con LangGraph

1. Define el estado del grafo con la pregunta, el historial de mensajes, los artículos recuperados, el borrador de respuesta y un contador de iteraciones.
2. Crea tres herramientas: `buscar_articulos(consulta, ley?)`, `obtener_articulo(ley, numero)` y `comparar(tema, leyes)`.
3. Arma el grafo con estos nodos. Un nodo de razonamiento decide qué herramienta usar o si ya puede responder. Un nodo de herramientas las ejecuta. Un nodo de generación redacta la respuesta con citas en formato `[LFT, art. 61]`. Un nodo verificador comprueba que cada cita exista entre los artículos recuperados y que la afirmación esté respaldada.
4. Si el verificador falla, el grafo regresa al razonamiento una vez más. Si vuelve a fallar o se alcanzan cinco iteraciones, responde que no hay evidencia suficiente.
5. Usa salidas estructuradas con Pydantic para la respuesta final (texto y lista de citas).

**Prompt para Claude Code.** Implementa la Fase 3 en src/articulia/agent. Dibuja el grafo resultante en docs/decisiones.md con un diagrama Mermaid. Agrega pruebas con un LLM simulado para el camino feliz, el reintento y la abstención.

**Terminado cuando** el agente responde con citas válidas, se abstiene ante una pregunta fuera del corpus (por ejemplo sobre una ley estatal) y las tres pruebas pasan.

### Fase 4. API con FastAPI

1. Endpoints `POST /ask`, `POST /ask/stream` (SSE con los pasos del agente y la respuesta), `GET /laws`, `GET /articles/{ley}/{numero}` y `GET /health`.
2. Validación de entradas con Pydantic, longitud máxima de la pregunta y manejo de errores con respuestas claras.
3. Una defensa básica contra prompt injection: el texto recuperado se trata como datos dentro del prompt y nunca como instrucciones.
4. Agrega la API como servicio en Docker Compose.

**Prompt para Claude Code.** Implementa la Fase 4 y agrega pruebas de integración con TestClient. Documenta los endpoints en el README.

**Terminado cuando** `docker compose up` levanta base y API, y `/docs` muestra la documentación de OpenAPI.

### Fase 5. Frontend

1. Una vista de chat que consume `/ask/stream` y muestra los pasos del agente mientras trabaja.
2. Cada cita es clickeable y abre un panel lateral con el texto completo del artículo.
3. Un selector para filtrar por ley.

**Prompt para Claude Code.** Implementa la Fase 5 en frontend/ con React, Vite y TypeScript. Prioriza que las citas y el panel del artículo se vean claros; es lo que se mostrará en la demo.

**Terminado cuando** puedes grabar una demo de 30 segundos haciendo una pregunta y abriendo una cita.

### Fase 6. Evaluación y observabilidad

1. Escribe tú `eval/dataset.jsonl` con 60 preguntas. Cada una lleva la pregunta, la ley y artículos esperados, y una respuesta de referencia breve. Diez de ellas deben ser preguntas sin respuesta en el corpus.
2. Activa LangSmith con las variables de entorno para registrar cada ejecución.
3. Implementa `run_eval.py`, que corre el dataset, calcula las métricas de la sección Evaluación y guarda una tabla en `eval/results/`.

**Prompt para Claude Code.** Implementa run\_eval.py usando Ragas para fidelidad y relevancia, y calcula a mano hit@5, MRR y la tasa de abstención correcta. El script debe imprimir una tabla Markdown lista para el README.

**Terminado cuando** tienes una primera tabla de resultados. Luego haz al menos una iteración de mejora (por ejemplo ajustar el reranker o el prompt) y documenta el antes y el después.

### Fase 7. CI con GitHub Actions

1. Un workflow que en cada push corre ruff y pytest.
2. Un segundo job, solo en pull requests, que corre una evaluación rápida con 10 preguntas y falla si hit@5 baja del umbral. Usa secretos del repositorio para la API key.

**Prompt para Claude Code.** Implementa la Fase 7. Usa servicios de GitHub Actions para levantar PostgreSQL con pgvector en el job de evaluación.

**Terminado cuando** el badge de CI aparece en verde en el README.

### Fase 8. Servidor MCP

1. En `mcp_server.py`, expón `buscar_articulos`, `obtener_articulo` y `preguntar` con el SDK oficial de MCP para Python, reutilizando las funciones del paquete.
2. Valida entradas y devuelve errores claros.
3. Pruébalo conectándolo a Claude Desktop y documenta la configuración en el README.

**Prompt para Claude Code.** Implementa la Fase 8 con transporte stdio y agrega en el README el bloque de configuración para Claude Desktop.

**Terminado cuando** Claude Desktop puede preguntarle a ArticulIA y recibir artículos citados.

### Opcional A. Voz

Un endpoint que recibe audio, lo transcribe con faster-whisper, pasa el texto al agente y devuelve la respuesta en audio con un TTS en español. Te conecta directamente con la vacante de Resolv Global y con tus proyectos de voz.

### Opcional B. Despliegue

Despliega el Compose completo en tu VPS de Hostinger con un dominio y HTTPS, para que los reclutadores puedan probarlo sin instalar nada.

## Evaluación y métricas

La tabla de métricas en el README es lo que distingue este proyecto de un chatbot más. Las metas son puntos de partida razonables; lo importante es medir, mejorar una vez y documentar el cambio.

| Métrica | Qué mide | Cómo se calcula | Meta inicial |
| --- | --- | --- | --- |
| Hit@5 | Si el artículo esperado aparece entre los 5 recuperados | Propio, contra `dataset.jsonl` | ≥ 0.85 |
| MRR | Qué tan arriba aparece el artículo correcto | Propio | ≥ 0.70 |
| Fidelidad | Si cada afirmación está respaldada por los artículos citados | Ragas (faithfulness) | ≥ 0.85 |
| Relevancia de la respuesta | Si la respuesta atiende la pregunta | Ragas (answer relevancy) | ≥ 0.80 |
| Citas válidas | Porcentaje de citas que existen y fueron recuperadas | Propio, desde la salida estructurada | 100 % |
| Abstención correcta | Si responde que no hay evidencia en las 10 preguntas sin respuesta | Propio | ≥ 0.80 |
| Latencia p50 y p95 | Tiempo por consulta | LangSmith | Reportar |
| Costo por consulta | Tokens por consulta en el LLM elegido | LangSmith | Reportar |

Para el dataset, reparte las 60 preguntas entre las seis leyes y mezcla tres tipos. Preguntas directas ("¿cuántos días de vacaciones corresponden al primer año?"), preguntas que requieren dos artículos o dos leyes, y preguntas sin respuesta en el corpus. Escríbelas en el lenguaje en que las haría una persona sin formación legal, no copiando el texto del artículo, porque eso inflaría las métricas.

## Cierre, README y CV

### Lista de terminado

- [ ] `docker compose up` levanta base, API y frontend en una máquina limpia
- [ ] El agente cita artículos válidos y se abstiene cuando no hay evidencia
- [ ] Tabla de métricas publicada, con al menos una iteración de mejora documentada
- [ ] CI en verde con badge en el README
- [ ] Servidor MCP probado en Claude Desktop
- [ ] Demo grabada en GIF o video corto
- [ ] `docs/decisiones.md` explica cada elección importante

### Qué debe tener el README

1. Una línea que diga qué hace y el GIF de la demo justo debajo.
2. Diagrama de arquitectura (el Mermaid de la Fase 3 sirve).
3. Cómo correrlo en tres comandos.
4. La tabla de métricas con la fecha de la evaluación.
5. Decisiones técnicas en cinco o seis viñetas, por ejemplo por qué corte por artículo, por qué búsqueda híbrida y por qué un verificador de citas.
6. Limitaciones honestas, como que el corpus es de seis leyes federales y no sustituye asesoría legal.

### Cómo ponerlo en el CV

Rellena los corchetes con tus resultados reales al terminar la Fase 6.

**ArticulIA, agente de consulta legislativa con citas verificables**

- Desarrollé un agente en LangGraph que responde preguntas sobre \[6\] leyes federales mexicanas citando el artículo exacto, con un nodo verificador que obliga a abstenerse cuando no hay evidencia.
- Implementé búsqueda híbrida (pgvector y texto completo en PostgreSQL) con reranking, alcanzando \[X\] de hit@5 y \[Y\] de fidelidad medidos con Ragas sobre un dataset propio de \[60\] preguntas.
- Expuse el sistema con FastAPI y como servidor MCP, contenerizado con Docker Compose, con CI en GitHub Actions y trazas en LangSmith.

**English version**

- Built a LangGraph agent that answers questions about \[6\] Mexican federal laws citing the exact article, with a verifier node that forces abstention when evidence is missing.
- Implemented hybrid search (pgvector and PostgreSQL full-text) with reranking, reaching \[X\] hit@5 and \[Y\] faithfulness measured with Ragas on a custom \[60\]-question dataset.
- Served the system through FastAPI and as an MCP server, containerized with Docker Compose, with GitHub Actions CI and LangSmith tracing.
