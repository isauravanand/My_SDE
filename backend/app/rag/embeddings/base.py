from abc import ABC, abstractmethod


class EmbeddingError(Exception):
    """Base exception for embedding provider errors."""

    def __init__(self, message: str, status_code: int = 500, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class EmbeddingConfigError(EmbeddingError):
    """Raised when embedding provider credentials or configuration are missing."""

    def __init__(self, message: str = "Embedding provider is not properly configured"):
        super().__init__(message, status_code=503)


class EmbeddingRateLimitError(EmbeddingError):
    """Raised when embedding provider rate limit is encountered."""

    def __init__(self, message: str = "Embedding provider rate limit exceeded", retry_after: int | None = None):
        super().__init__(message, status_code=429, details={"retry_after": retry_after})
        self.retry_after = retry_after


class BaseEmbeddingProvider(ABC):
    """Abstract interface for dense text and code embeddings."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the embedding model."""
        pass

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Dimension count of output embedding vectors."""
        pass

    @property
    @abstractmethod
    def is_fake(self) -> bool:
        """Return True if this provider generates deterministic offline vectors for tests."""
        pass

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text chunks, returning a list of float vectors."""
        pass

    async def embed_query(self, query: str) -> list[float]:
        """Embed a single search query, returning a float vector."""
        vectors = await self.embed_texts([query])
        if not vectors or len(vectors) != 1:
            raise EmbeddingError("Failed to generate embedding for query")
        return vectors[0]
