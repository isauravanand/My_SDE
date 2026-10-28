import math

import pytest

from app.rag.embeddings.base import EmbeddingConfigError
from app.rag.embeddings.fake import DeterministicFakeEmbeddingProvider
from app.rag.embeddings.openai import OpenAIEmbeddingProvider


@pytest.mark.asyncio
async def test_fake_embedding_provider_properties_and_normalization():
    provider = DeterministicFakeEmbeddingProvider(model_name="mock-384", dimensions=384)
    assert provider.dimensions == 384
    assert provider.model_name == "mock-384"
    assert provider.is_fake is True

    vectors = await provider.embed_texts([
        "def authenticate_user(email, password):",
        "import numpy as np",
    ])
    assert len(vectors) == 2
    for vec in vectors:
        assert len(vec) == 384
        # Verify L2 norm is 1.0 (within float tolerance)
        l2_norm = math.sqrt(sum(x * x for x in vec))
        assert abs(l2_norm - 1.0) < 1e-4


@pytest.mark.asyncio
async def test_fake_embedding_determinism_and_similarity():
    provider = DeterministicFakeEmbeddingProvider(dimensions=384)

    text_a = "def verify_password(hash, password):"
    text_b = "def check_user_password(password_hash, raw_password):"
    text_c = "render_blue_button_ui_component()"

    vec_a = await provider.embed_query(text_a)
    vec_a2 = await provider.embed_query(text_a)
    vec_b = await provider.embed_query(text_b)
    vec_c = await provider.embed_query(text_c)

    # Identical text yields exact same vector
    assert vec_a == vec_a2

    # Dot product between related password/hash texts should be higher than unrelated UI button
    sim_ab = sum(x * y for x, y in zip(vec_a, vec_b, strict=True))
    sim_ac = sum(x * y for x, y in zip(vec_a, vec_c, strict=True))

    assert sim_ab > sim_ac


def test_openai_provider_missing_key():
    with pytest.raises(EmbeddingConfigError):
        OpenAIEmbeddingProvider(api_key=None)
