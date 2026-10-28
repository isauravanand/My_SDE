import asyncio
import logging
from typing import Any

import httpx

from app.rag.embeddings.base import (
    BaseEmbeddingProvider,
    EmbeddingConfigError,
    EmbeddingError,
    EmbeddingRateLimitError,
)

logger = logging.getLogger(__name__)


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """Embedding provider connecting to OpenAI or OpenAI-compatible embedding endpoints."""

    def __init__(
        self,
        api_key: str | None,
        model_name: str = "text-embedding-3-small",
        dimensions: int = 1536,
        base_url: str | None = None,
        max_retries: int = 3,
        timeout_seconds: float = 20.0,
    ):
        if not api_key:
            raise EmbeddingConfigError("EMBEDDING_API_KEY is required for OpenAI embedding provider")
        self._api_key = api_key
        self._model_name = model_name
        self._dimensions = dimensions
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._max_retries = max_retries
        self._timeout_seconds = timeout_seconds

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def is_fake(self) -> bool:
        return False

    async def _request_batch(self, batch_texts: list[str]) -> list[list[float]]:
        url = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self._model_name,
            "input": batch_texts,
        }

        # text-embedding-3 supports optional dimensions parameter
        if "text-embedding-3" in self._model_name:
            payload["dimensions"] = self._dimensions

        for attempt in range(1, self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=payload)

                if response.status_code == 429:
                    retry_header = response.headers.get("retry-after")
                    retry_after = int(retry_header) if retry_header and retry_header.isdigit() else 2**attempt
                    if attempt == self._max_retries:
                        raise EmbeddingRateLimitError(
                            "OpenAI rate limit exceeded after maximum retries",
                            retry_after=retry_after,
                        )
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code >= 500:
                    if attempt == self._max_retries:
                        raise EmbeddingError(
                            f"OpenAI server error ({response.status_code}): {response.text}",
                            status_code=response.status_code,
                        )
                    await asyncio.sleep(1.0 * (2 ** (attempt - 1)))
                    continue

                if response.status_code >= 400:
                    raise EmbeddingError(
                        f"OpenAI API client error ({response.status_code}): {response.text}",
                        status_code=response.status_code,
                    )

                data = response.json()
                raw_items = data.get("data", [])
                # Ensure ordered by index
                raw_items.sort(key=lambda x: x.get("index", 0))

                vectors: list[list[float]] = []
                for item in raw_items:
                    vec = item["embedding"]
                    if len(vec) != self._dimensions:
                        logger.warning(
                            f"Received vector with dim {len(vec)}, expected {self._dimensions}."
                        )
                    vectors.append(vec)

                return vectors

            except httpx.TimeoutException as e:
                if attempt == self._max_retries:
                    raise EmbeddingError("Connection to embedding provider timed out", status_code=504) from e
                await asyncio.sleep(1.0 * (2 ** (attempt - 1)))
            except httpx.RequestError as e:
                if attempt == self._max_retries:
                    raise EmbeddingError(f"Network error calling embedding provider: {e}", status_code=502) from e
                await asyncio.sleep(1.0 * (2 ** (attempt - 1)))

        raise EmbeddingError("Failed to fetch embeddings after retries")

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        # Split into batches of at most 64 texts
        batch_size = 64
        all_vectors: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            batch_result = await self._request_batch(chunk)
            all_vectors.extend(batch_result)

        return all_vectors
