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
    rerank_candidates: int = 20
    # En CPU el reranker tarda ~7 s por consulta (20 candidatos); se puede apagar para desarrollo.
    reranker_enabled: bool = True

    # LangSmith
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "articulia"


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración cacheada."""
    return Settings()
