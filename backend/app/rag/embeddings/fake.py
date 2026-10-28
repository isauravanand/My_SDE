import hashlib
import math
import re

from app.rag.embeddings.base import BaseEmbeddingProvider


class DeterministicFakeEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic, offline embedding provider for tests and unconfigured local environments.

    Maps words and character n-grams to pseudo-random indices in a dense vector,
    normalizing to unit length (L2 norm = 1.0). This provides genuine cosine similarity
    proportional to token and n-gram overlap without requiring any external network requests.
    """

    def __init__(self, model_name: str = "mock-embed-384", dimensions: int = 384):
        self._model_name = model_name
        self._dimensions = dimensions

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def is_fake(self) -> bool:
        return True

    def _hash_token(self, token: str) -> tuple[int, float]:
        """Hash token into (index, sign) in the vector space."""
        h = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "big") % self._dimensions
        # Use next byte to determine sign (+1.0 or -1.0)
        sign = 1.0 if (h[4] % 2 == 0) else -1.0
        return idx, sign

    def _embed_single(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        if not text.strip():
            # Return uniform unit vector
            val = 1.0 / math.sqrt(self._dimensions)
            return [val] * self._dimensions

        # Tokenize words and subwords
        tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())

        # Include 3-char ngrams for subword matching
        ngrams: list[str] = []
        for t in tokens:
            if len(t) >= 4:
                for i in range(len(t) - 2):
                    ngrams.append(t[i : i + 3])

        all_features = tokens + ngrams
        if not all_features:
            val = 1.0 / math.sqrt(self._dimensions)
            return [val] * self._dimensions

        # Feature hashing (hashing trick)
        for feat in all_features:
            idx, sign = self._hash_token(feat)
            vector[idx] += sign

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0.0:
            vector = [x / norm for x in vector]
        else:
            val = 1.0 / math.sqrt(self._dimensions)
            vector = [val] * self._dimensions

        return vector

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_single(t) for t in texts]
