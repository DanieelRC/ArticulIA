import pytest
from pydantic import ValidationError

from articulia.config import Settings


def test_lee_variables_de_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:1234/db")

    s = Settings(_env_file=None)

    assert s.llm_provider == "anthropic"
    assert s.llm_model == "claude-sonnet-5-5"
    assert s.database_url == "postgresql://u:p@host:1234/db"


def test_rechaza_proveedor_desconocido(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "otro")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_api_key_no_se_imprime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "clave-secreta")
    s = Settings(_env_file=None)
    assert "clave-secreta" not in repr(s)
    assert s.google_api_key is not None
    assert s.google_api_key.get_secret_value() == "clave-secreta"


def test_api_key_vacia_da_error_claro(monkeypatch: pytest.MonkeyPatch) -> None:
    from articulia.llm import get_llm

    monkeypatch.setenv("GOOGLE_API_KEY", "")
    with pytest.raises(RuntimeError, match="Falta la API key"):
        get_llm(Settings(_env_file=None))
