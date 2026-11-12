"""Fábrica del modelo de chat según LLM_PROVIDER (gemini, anthropic o xai)."""

from langchain_core.language_models import BaseChatModel

from articulia.config import Settings, get_settings


def get_llm(settings: Settings | None = None) -> BaseChatModel:
    """Crea el modelo configurado. Cambiar de proveedor no requiere tocar código."""
    s = settings or get_settings()

    def key(secret: object) -> str:
        if secret is None:
            raise RuntimeError(f"Falta la API key para LLM_PROVIDER={s.llm_provider} en .env")
        return secret.get_secret_value()  # type: ignore[attr-defined]

    if s.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=s.llm_model, api_key=key(s.google_api_key), temperature=0
        )
    if s.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=s.llm_model, api_key=key(s.anthropic_api_key), temperature=0)
    from langchain_xai import ChatXAI

    return ChatXAI(model=s.llm_model, api_key=key(s.xai_api_key), temperature=0)
