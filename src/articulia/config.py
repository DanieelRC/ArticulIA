"""Configuración del proyecto, leída solo de variables de entorno y `.env`."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables de entorno de ArticulIA."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    llm_provider: Literal["gemini", "anthropic", "xai"] = "gemini"
    llm_model: str = "gemini-2.5-flash"
    google_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    xai_api_key: SecretStr | None = None

    # Base de datos
    database_url: str = "postgresql://articulia:articulia@localhost:5432/articulia"

    # Recuperación
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rrf_k: int = 60
    # Peso del texto completo en RRF (el vectorial pesa 1). Ver docs/decisiones.md, Fase 6.
    rrf_text_weight: float = 0.5
    rerank_candidates: int = 20
    # Cascada de reranking, elegida con eval/bench_reranker.py (ver docs/decisiones.md).
    rerank_max_length: int = 256
    reranker_int8: bool = True
    rerank_prefilter_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"  # "" lo apaga
    rerank_prefilter_keep: int = 8
    # Se puede apagar para desarrollo: la búsqueda baja de ~4 s a ~0.5 s y pierde calidad.
    reranker_enabled: bool = True

    # Control de gasto y abuso (ver articulia/api/limits.py)
    environment: Literal["development", "production"] = "development"
    daily_budget_usd: float = 1.0
    # Precio por millón de tokens del modelo configurado (grok-build-0.1: 1.00 / 2.00 USD).
    llm_price_in_per_m: float = 1.0
    llm_price_out_per_m: float = 2.0
    rate_limit_per_minute: int = 5
    rate_limit_per_day: int = 30
    max_concurrent_agents: int = 2
    answer_cache_ttl_hours: int = 168
    # Topes por llamada y por consulta: una pregunta no puede dispararse.
    llm_max_output_tokens: int = 4000
    llm_timeout_s: float = 90.0
    llm_max_retries: int = 1
    max_tokens_per_query: int = 40_000
    # Cargar embeddings y reranker al arrancar la API (la primera pregunta no paga la carga).
    warmup_models: bool = False

    # LangSmith
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "articulia"


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración cacheada."""
    return Settings()


def configurar_trazas(settings: Settings | None = None) -> bool:
    """Activa LangSmith si LANGSMITH_TRACING=true y hay API key.

    LangChain lee las variables `LANGSMITH_*` de `os.environ`, pero pydantic-settings solo las
    carga en `Settings` cuando vienen de `.env`; aquí se copian al entorno del proceso.
    Devuelve True si las trazas quedaron activas.
    """
    import os

    s = settings or get_settings()
    key = s.langsmith_api_key.get_secret_value().strip() if s.langsmith_api_key else ""
    activo = s.langsmith_tracing and bool(key)
    os.environ["LANGSMITH_TRACING"] = "true" if activo else "false"
    if activo:
        os.environ["LANGSMITH_API_KEY"] = key
        os.environ["LANGSMITH_PROJECT"] = s.langsmith_project
    return activo
