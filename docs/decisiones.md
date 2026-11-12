# Decisiones técnicas

Registro de por qué se eligió cada pieza. Una entrada por decisión no obvia.

## Fase 0. Preparación

### uv como gestor de dependencias
Resuelve e instala mucho más rápido que pip/poetry, genera `uv.lock` reproducible y además
instala la versión de Python indicada en `.python-version` (3.12) sin depender del Python del sistema.

### Layout `src/articulia/` (paquete instalable)
`uv init --package` crea un paquete instalable en modo editable. Así las pruebas, la API, la
evaluación y el servidor MCP importan `articulia` igual, y se evita que los tests pasen por
importar archivos sueltos desde la raíz del repo.

### Imagen `pgvector/pgvector:pg16`
Es PostgreSQL 16 oficial con la extensión `vector` ya compilada. La extensión se habilita en
`src/articulia/db/init/001_extensions.sql`, montado en `/docker-entrypoint-initdb.d`, que
Postgres ejecuta solo la primera vez que crea el volumen. Una sola base sirve para la búsqueda
vectorial (pgvector) y la de texto completo (`tsvector` en español), sin un vector store aparte.

### Configuración con pydantic-settings
`config.py` define un único `Settings` validado que lee variables de entorno y `.env`.
`get_settings()` va cacheado para no releer el archivo en cada llamada; en pruebas se limpia
la caché con `get_settings.cache_clear()`.

### Prueba de base de datos que se salta sin Docker
`tests/test_db.py` se marca como `skip` si no puede conectarse, para que `pytest` no falle en
máquinas sin la base levantada. En CI (Fase 7) la base estará disponible y la prueba sí correrá.

## Fase 1. Corpus e ingesta

### PyMuPDF directo, sin loaders de LangChain
Los PDFs de LeyesBiblio son texto nativo (no escaneado), y `pymupdf` da el texto por página, que
es justo lo que hace falta para quitar el encabezado repetido. Un loader de LangChain solo
envolvería la misma llamada y agregaría una dependencia pesada en esta fase. LangChain entra en
la Fase 3, donde sí aporta.

### Limpieza de páginas
Cada página empieza con el mismo encabezado (nombre de la ley, Cámara, "Última Reforma DOF ...")
y termina en la línea "N de M". Se descarta todo hasta esa línea; no hay pie de página. La fecha
de última reforma se toma de la portada.

### Cómo se reconoce un encabezado de artículo
Una expresión regular cubre las variantes reales del corpus: `Artículo 5o.-`, `ARTICULO 1º.-`,
`Artículo 123 Bis.-`, `Artículo 103-Bis.-`, `Artículo 65 Bis 7.`, `Artículo 39-A.-`,
`Artículo 410 A.-`, `Artículos 135.-` (errata del PDF). Para evitar falsos positivos:
- Solo con "Artículo" en mayúscula inicial: las referencias internas van en minúscula ("el artículo 82").
- El sufijo (Bis, -A) va antes del terminador, así "Artículo 14. A ninguna ley..." no se lee como 14-A.
- La línea anterior debe cerrar oración, estar vacía o ser una nota/encabezado, para no confundir
  una referencia partida por salto de línea con un artículo nuevo.
- La numeración debe ser ascendente: un "Artículo 54.-" que aparece tras el 1777 es una cita
  de otra ley dentro de una "Nota:" editorial, no un artículo del Código.

Los números se normalizan (`5o.` → `5`, `103-Bis` → `103 Bis`, `410 A` → `410-A`) y el id es
`<LEY>-<numero>` (`LFT-61`, `LFT-42_Bis`), o `<LEY>-T-<numero>` para transitorios.

### Notas de reforma fuera del texto
Líneas como "Párrafo reformado DOF 10-06-2011" se guardan en `reformas` y no en `texto`: no son
contenido legal y meterían ruido en los embeddings y en la búsqueda de texto completo.

### Transitorios: solo los del texto original
Se guardan los transitorios de la publicación original de cada ley (`tipo="transitorio"`). Los de
"ARTÍCULOS TRANSITORIOS DE DECRETOS DE REFORMA" (cientos de decretos con numeración repetida
PRIMERO, SEGUNDO...) se descartan por ahora. Limitación: el régimen de entrada en vigor de una
reforma reciente vive ahí, y el agente no lo verá.

### Validación de la división
`python -m articulia.ingest` imprime, por ley, el número de artículos, derogados, transitorios,
último número, huecos en la numeración (1..último) y ids duplicados. Huecos o duplicados indican un
encabezado mal reconocido; `tests/test_corpus.py` los convierte en prueba.

| Ley | Permanentes | Núm. simples | Derogados | Transitorios | Último |
| --- | ---: | ---: | ---: | ---: | ---: |
| CCF | 3103 | 3074 | 183 | 9 | 3074 |
| CPEUM | 136 | 136 | 0 | 19 | 136 |
| LFDA | 259 | 238 | 0 | 9 | 238 |
| LFPC | 190 | 143 | 9 | 5 | 143 |
| LFPDPPP | 64 | 64 | 0 | 20 | 64 |
| LFT | 1262 | 1010 | 148 | 13 | 1010 |

"Permanentes" incluye Bis, Ter, -A, etc. Los 21 primeros artículos del CCF (Disposiciones
Preliminares) no tienen título ni capítulo; es correcto.

## Fase 2. Indexación y búsqueda híbrida

### Dos tablas: `articles` para citar, `chunks` para embeddings
El plan pedía un `vector(1024)` por artículo, pero bge-m3 trunca a 512 tokens y hay artículos
enormes: LFT 513 (tabla de enfermedades de trabajo) tiene 288 mil caracteres y CPEUM 123, 31 mil.
Con un solo vector, todo lo que pasa del token 512 sería invisible para la búsqueda vectorial.
- `articles`: un renglón por artículo con metadatos, texto completo y `tsvector`. Es lo que se cita.
- `chunks`: fragmentos de ≤1500 caracteres (~400 tokens), cortados por párrafo, cada uno con su
  embedding y su `article_id`. Cada fragmento empieza con "Ley Federal del Trabajo, artículo 61.
  Capítulo II. Jornada de trabajo" para que una fracción suelta conserve su contexto.
- La búsqueda vectorial toma la distancia del mejor fragmento de cada artículo. La unidad que
  devuelve la búsqueda sigue siendo el artículo.
- Resultado: 5,089 artículos y 5,524 fragmentos. Los derogados se guardan en `articles` (para
  `obtener_articulo`) pero no se fragmentan, porque "Se deroga." solo mete ruido.

### Texto completo en español sin acentos
Configuración `es` = `spanish` + `unaccent`, para que "jornada maxima" encuentre "máxima". La
consulta se convierte de AND a OR (`plainto_tsquery` → `|`): una pregunta en lenguaje natural casi
nunca tiene todas sus palabras en un mismo artículo. `ts_rank` con normalización 1 (divide entre el
log de la longitud) evita que los artículos gigantes ganen por tener más palabras.

### Por qué RRF y k = 60
Reciprocal Rank Fusion: `score(d) = Σ 1 / (k + rango_i(d))`. Usa solo posiciones, así que no hay
que calibrar distancias coseno contra puntajes de `ts_rank`, que viven en escalas distintas y
cambian de una consulta a otra. k = 60 es el valor del artículo original (Cormack et al., 2009) y el
estándar de facto: con k grande, aparecer en ambas listas pesa más que quedar primero en solo una.
Se puede ajustar con `RRF_K` y se revisará con la evaluación de la Fase 6.

### HNSW con escaneo iterativo
Índice HNSW (`m=16`, `ef_construction=64`) sobre los fragmentos. Con filtro por ley, HNSW puede
devolver menos filas de las pedidas porque filtra después de buscar; `hnsw.iterative_scan =
relaxed_order` (pgvector ≥ 0.8) sigue recorriendo el índice hasta juntar suficientes.

### Indexación idempotente
Cada artículo guarda un hash de su contenido. Al reindexar solo se recalculan embeddings de los que
cambiaron, y se borran los que ya no están en el corpus. La primera indexación tarda 40 min en CPU
(Ryzen 5 4600H, ~1,200 caracteres/s); las siguientes, segundos.

### El reranker en CPU es el cuello de botella
| Etapa | Latencia (CPU, sin GPU) |
| --- | --- |
| Búsqueda híbrida (embedding de la consulta + vector + texto + RRF) | ~300 ms |
| Reranker bge-reranker-v2-m3, 20 candidatos, lote 32 | 20.6 s |
| Reranker, lote 4 (rellenar al fragmento más largo de un lote grande cuesta caro) | 8.6 s |

El reranker sí mejora el orden: en "jornada máxima de trabajo" sube LFT 61 del lugar 14 al 5. El
criterio de "menos de un segundo" se cumple con la búsqueda híbrida. El reranker queda detrás de
`RERANKER_ENABLED` para poder apagarlo en desarrollo. Que se quede encendido, se cambie por uno más
ligero o se cuantice se decidirá con números de la Fase 6.

### Hallazgo: LFT 59 tras la reforma de 2026
La prueba de la guía pide LFT 61 para "jornada máxima de trabajo". Con la reforma publicada en el
DOF el 01-05-2026, el artículo 59 dice "La duración máxima de la jornada ordinaria de trabajo será
de cuarenta horas semanales", y el reranker lo pone primero. La prueba exige ambos (59 y 61) en el top 5.

## Fase 3. Agente con LangGraph

### Grafo

```mermaid
graph TD
    START([inicio]) --> razonar
    razonar -- pide herramientas --> herramientas
    herramientas --> razonar
    razonar -- ya puede responder --> generar
    razonar -- 5 iteraciones --> abstenerse
    generar --> verificar
    verificar -- citas válidas y respaldadas --> FIN([fin])
    verificar -- sin_evidencia del modelo --> FIN
    verificar -- falla, primer intento --> razonar
    verificar -- falla otra vez o 5 iteraciones --> abstenerse
    abstenerse --> FIN
```

- **razonar**: el LLM con las tres herramientas enlazadas decide qué buscar o si ya basta.
- **herramientas**: ejecuta las llamadas, valida argumentos con Pydantic y guarda lo recuperado en
  `state["articulos"]`. Un error (argumento faltante, ley inexistente) vuelve al modelo como
  `ToolMessage` para que corrija, en vez de romper el grafo.
- **generar**: salida estructurada `Respuesta {respuesta, citas, sin_evidencia}`.
- **verificar**: dos capas. Primero una determinista: cada cita `[LEY, art. N]` del texto debe estar
  entre los artículos recuperados en esta conversación (no basta con que exista en la base: el
  modelo tuvo que leerla). Si pasa, un juicio del LLM con salida `Verificacion {respaldada,
  problemas}` revisa que cada afirmación diga lo que dice el artículo citado.
- **abstenerse**: respuesta fija que explica el alcance del corpus. No pasa por el LLM, para que la
  abstención nunca invente.

### Nodo de herramientas propio en vez de `ToolNode`
`ToolNode` de LangGraph solo agrega `ToolMessage`s. El verificador necesita saber qué artículos se
recuperaron (para comparar las citas), así que el nodo propio actualiza también
`state["articulos"]` con un reducer que fusiona diccionarios. Además aplica el filtro de ley que
el usuario eligió en la interfaz, aunque el modelo olvide pasarlo.

### Las citas salen del texto, no del campo `citas`
El texto es lo que lee la persona. Si el modelo pone una cita en el texto que no está en `citas`,
o al revés, manda el texto: las citas se extraen con regex (`extraer_citas`) y el campo
estructurado queda como respaldo.

### Artículos como datos, no instrucciones
Todo texto recuperado se envuelve en `<articulo id=... cita=...>...</articulo>` y los tres prompts
dicen que lo de adentro es material de consulta. `formatear_articulo` elimina cualquier
`</articulo>` dentro del texto para que un documento no pueda cerrar la etiqueta y colar órdenes.

### Inyección de dependencias para probar sin LLM ni base
`build_graph(llm, corpus)` recibe el modelo y un `Corpus` (protocolo con `buscar` y `obtener`).
Las pruebas usan un LLM guionizado y un corpus en memoria con texto real de la LFT y cubren el
camino feliz, el reintento tras una cita no recuperada, la abstención tras dos fallos, la abstención
del propio modelo, el límite de iteraciones y el error de herramienta.
`tests/test_agent_real.py` corre de punta a punta con el LLM configurado y se salta sin API key.

### Proveedor por variable de entorno
`articulia/llm.py` crea `ChatGoogleGenerativeAI`, `ChatAnthropic` o `ChatXAI` según
`LLM_PROVIDER`, siempre con temperatura 0. Los tres soportan `bind_tools` y
`with_structured_output`, que es todo lo que usa el grafo.
