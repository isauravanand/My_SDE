from app.core.config import settings
from app.planning.llm.base import BaseLLMProvider
from app.planning.llm.mock import MockLLMProvider
from app.planning.llm.openai import OpenAILLMProvider


def get_llm_provider(
    provider_name: str | None = None,
    **kwargs,
) -> BaseLLMProvider:
    """Return the configured LLM provider instance."""
    provider = (provider_name or settings.LLM_PROVIDER).lower()

    if provider == "openai":
        return OpenAILLMProvider(**kwargs)
    elif provider == "groq":
        from app.planning.llm.groq import GroqLLMProvider

        return GroqLLMProvider(**kwargs)
    elif provider == "mock":
        return MockLLMProvider(**kwargs)
    else:
        # Default fallback to mock provider for safe offline execution
        return MockLLMProvider(**kwargs)
