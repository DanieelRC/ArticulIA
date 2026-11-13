# API de ArticulIA (FastAPI + agente + modelos locales en CPU).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/models

WORKDIR /app

# Dependencias primero: esta capa solo se reconstruye si cambia el lockfile.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

EXPOSE 8000
# Proceso sin privilegios: si algo se compromete, no es root dentro del contenedor.
RUN useradd --create-home --uid 10001 app && mkdir -p /models && chown app /models
USER app

# --proxy-headers: la IP del cliente llega en X-Forwarded-For desde nginx, que la sobrescribe.
# La API no se publica a internet; solo nginx, dentro de la red de Compose, puede alcanzarla.
CMD ["uvicorn", "articulia.api.main:app", "--host", "0.0.0.0", "--port", "8000",      "--proxy-headers", "--forwarded-allow-ips", "*"]
