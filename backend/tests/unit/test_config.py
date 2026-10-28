import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults():
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/testdb",
        SECRET_KEY="a" * 32,
    )
    assert settings.APP_NAME == "MySDE Backend"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.DB_POOL_SIZE == 10
    assert "http://localhost:5173" in settings.CORS_ORIGINS


def test_cors_origins_parsing():
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/testdb",
        SECRET_KEY="a" * 32,
        CORS_ORIGINS="https://app.mysde.dev/, https://mysde.dev",
    )
    assert settings.CORS_ORIGINS == ["https://app.mysde.dev", "https://mysde.dev"]


def test_invalid_database_url():
    with pytest.raises(ValidationError) as exc_info:
        Settings(DATABASE_URL="mysql://user:pass@localhost/db", SECRET_KEY="a" * 32)
    assert "DATABASE_URL must start with one of" in str(exc_info.value)


def test_production_secret_key_validation():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="production",
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/testdb",
            SECRET_KEY="short-key",
        )
    assert "SECRET_KEY must be at least 32 characters long" in str(exc_info.value)


def test_groq_llm_settings_configuration():
    # Valid groq config with API key
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/testdb",
        SECRET_KEY="a" * 32,
        LLM_PROVIDER="groq",
        LLM_MODEL="llama-3.3-70b-versatile",
        LLM_API_KEY="gsk_test123456789012345678901234567890",
    )
    assert settings.LLM_PROVIDER == "groq"
    assert settings.LLM_MODEL == "llama-3.3-70b-versatile"
    assert settings.is_llm_configured is True

    # Groq without API key should report is_llm_configured as False
    unconfigured = Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/testdb",
        SECRET_KEY="a" * 32,
        LLM_PROVIDER="groq",
        LLM_API_KEY=None,
    )
    assert unconfigured.is_llm_configured is False


def test_invalid_llm_provider_rejected():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/testdb",
            SECRET_KEY="a" * 32,
            LLM_PROVIDER="unsupported_provider",
        )
    assert "Input should be 'mock', 'openai', 'anthropic', 'gemini' or 'groq'" in str(exc_info.value)
