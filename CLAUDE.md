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
