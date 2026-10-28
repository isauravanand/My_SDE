from app.core.config import Settings, get_settings
from app.rag.embeddings.base import BaseEmbeddingProvider
from app.rag.embeddings.fake import DeterministicFakeEmbeddingProvider
from app.rag.embeddings.openai import OpenAIEmbeddingProvider


def get_embedding_provider(settings: Settings | None = None) -> BaseEmbeddingProvider:
    """Factory creating the configured embedding provider."""
    cfg = settings or get_settings()

    if cfg.EMBEDDING_PROVIDER == "openai":
        return OpenAIEmbeddingProvider(
            api_key=cfg.EMBEDDING_API_KEY,
            model_name=cfg.EMBEDDING_MODEL,
            dimensions=cfg.EMBEDDING_DIMENSIONS,
            base_url=cfg.EMBEDDING_BASE_URL,
        )

    # Default to deterministic fake embedding provider for local dev and testing
    return DeterministicFakeEmbeddingProvider(
        model_name=cfg.EMBEDDING_MODEL,
        dimensions=cfg.EMBEDDING_DIMENSIONS,
    )
