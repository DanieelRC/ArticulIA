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
