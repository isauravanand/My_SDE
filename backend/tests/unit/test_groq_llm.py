import json
from unittest.mock import AsyncMock, MagicMock

import groq
import httpx
import pytest
from pydantic import BaseModel, Field

from app.planning.llm.factory import get_llm_provider
from app.planning.llm.groq import GroqLLMProvider


class SamplePlanSchema(BaseModel):
    title: str = Field(..., description="Plan title")
    steps: list[str] = Field(default_factory=list, description="List of implementation steps")
    estimated_hours: int = Field(default=1, description="Estimated effort in hours")


def make_mock_completion(content: str, prompt_tokens: int = 15, completion_tokens: int = 25):
    """Helper creating a mock Groq ChatCompletion response."""
    message = MagicMock()
    message.content = content

    choice = MagicMock()
    choice.message = message

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens

    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = usage
    return completion


@pytest.mark.asyncio
async def test_groq_generate_structured_success():
    """Ensure Groq provider generates schema-validated structured output with correct metadata."""
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()

    json_payload = json.dumps({
        "title": "Refactor auth middleware",
        "steps": ["Extract token parser", "Add test cases"],
        "estimated_hours": 3,
    })
    mock_client.chat.completions.create = AsyncMock(
        return_value=make_mock_completion(json_payload, prompt_tokens=100, completion_tokens=50)
    )

    provider = GroqLLMProvider(
        api_key="gsk_test123",
        model_name="llama-3.3-70b-versatile",
        client=mock_client,
    )

    result, metadata = await provider.generate_structured(
        prompt="Design a refactor plan",
        system_prompt="You are a senior engineer",
        schema_class=SamplePlanSchema,
    )

    assert isinstance(result, SamplePlanSchema)
    assert result.title == "Refactor auth middleware"
    assert len(result.steps) == 2
    assert result.estimated_hours == 3

    assert metadata["provider"] == "groq"
    assert metadata["model"] == "llama-3.3-70b-versatile"
    assert metadata["prompt_tokens"] == 100
    assert metadata["completion_tokens"] == 50
    assert metadata["total_tokens"] == 150

    # Verify call parameters
    mock_client.chat.completions.create.assert_awaited_once()
    call_kwargs = mock_client.chat.completions.create.await_args.kwargs
    assert call_kwargs["model"] == "llama-3.3-70b-versatile"
    assert call_kwargs["response_format"] == {"type": "json_object"}
    assert len(call_kwargs["messages"]) == 2


@pytest.mark.asyncio
async def test_groq_generate_structured_cleans_markdown_code_fences():
    """Ensure Groq provider strips markdown ```json code blocks from output before validation."""
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()

    wrapped_content = (
        "```json\n"
        "{\n"
        '  "title": "Wrapped Plan",\n'
        '  "steps": ["Step 1"],\n'
        '  "estimated_hours": 2\n'
        "}\n"
        "```"
    )
    mock_client.chat.completions.create = AsyncMock(
        return_value=make_mock_completion(wrapped_content)
    )

    provider = GroqLLMProvider(api_key="gsk_test123", client=mock_client)
    result, _ = await provider.generate_structured(
        prompt="Test",
        system_prompt="Test system",
        schema_class=SamplePlanSchema,
    )

    assert result.title == "Wrapped Plan"
    assert result.steps == ["Step 1"]


@pytest.mark.asyncio
async def test_groq_generate_text_success():
    """Ensure Groq provider supports raw text generation without json_object constraint."""
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()

    diff_content = "diff --git a/main.py b/main.py\n+print('hello')"
    mock_client.chat.completions.create = AsyncMock(
        return_value=make_mock_completion(diff_content, prompt_tokens=40, completion_tokens=20)
    )

    provider = GroqLLMProvider(api_key="gsk_test123", client=mock_client)
    content, metadata = await provider.generate_text(
        prompt="Generate diff",
        system_prompt="You are a patch generator",
    )

    assert content == diff_content
    assert metadata["provider"] == "groq"
    assert metadata["prompt_tokens"] == 40
    assert metadata["completion_tokens"] == 20

    # Ensure response_format was NOT forced for raw text
    call_kwargs = mock_client.chat.completions.create.await_args.kwargs
    assert "response_format" not in call_kwargs


@pytest.mark.asyncio
async def test_groq_missing_api_key_raises_value_error():
    """Ensure invoking Groq without credentials raises a clear ValueError."""
    provider = GroqLLMProvider(api_key=None, client=None)
    # Clear settings API key if set in environment
    provider.api_key = None

    with pytest.raises(ValueError, match="LLM_API_KEY is not configured for GroqLLMProvider"):
        await provider.generate_structured("prompt", "sys", SamplePlanSchema)

    with pytest.raises(ValueError, match="LLM_API_KEY is not configured for GroqLLMProvider"):
        await provider.generate_text("prompt", "sys")


@pytest.mark.asyncio
async def test_groq_invalid_json_raises_value_error():
    """Ensure malformed non-JSON response raises controlled ValueError."""
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=make_mock_completion("This is plain text, not JSON.")
    )

    provider = GroqLLMProvider(api_key="gsk_test123", client=mock_client)
    with pytest.raises(ValueError, match="did not return valid JSON"):
        await provider.generate_structured("prompt", "sys", SamplePlanSchema)


@pytest.mark.asyncio
async def test_groq_schema_validation_failure_raises_value_error():
    """Ensure output violating Pydantic schema constraints raises controlled ValueError."""
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    # Missing required field 'title', and 'estimated_hours' is string instead of int
    invalid_data = json.dumps({"steps": 12345})
    mock_client.chat.completions.create = AsyncMock(
        return_value=make_mock_completion(invalid_data)
    )

    provider = GroqLLMProvider(api_key="gsk_test123", client=mock_client)
    with pytest.raises(ValueError, match="does not satisfy schema 'SamplePlanSchema'"):
        await provider.generate_structured("prompt", "sys", SamplePlanSchema)


@pytest.mark.asyncio
async def test_groq_authentication_error_handling():
    """Ensure Groq 401 AuthenticationError is mapped to descriptive RuntimeError."""
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()

    mock_resp = httpx.Response(401, request=httpx.Request("POST", "https://api.groq.com"))
    auth_err = groq.AuthenticationError("Invalid API Key provided", response=mock_resp, body=None)
    mock_client.chat.completions.create = AsyncMock(side_effect=auth_err)

    provider = GroqLLMProvider(api_key="gsk_bad_key", client=mock_client)
    with pytest.raises(RuntimeError, match="Groq authentication failed \\(401\\)"):
        await provider.generate_structured("prompt", "sys", SamplePlanSchema)


@pytest.mark.asyncio
async def test_groq_rate_limit_error_handling():
    """Ensure Groq 429 RateLimitError is mapped to descriptive RuntimeError."""
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()

    mock_resp = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com"))
    rate_err = groq.RateLimitError("Rate limit reached for requests per minute", response=mock_resp, body=None)
    mock_client.chat.completions.create = AsyncMock(side_effect=rate_err)

    provider = GroqLLMProvider(api_key="gsk_test123", client=mock_client)
    with pytest.raises(RuntimeError, match="Groq rate limit exceeded \\(429\\)"):
        await provider.generate_structured("prompt", "sys", SamplePlanSchema)


@pytest.mark.asyncio
async def test_groq_timeout_error_handling():
    """Ensure Groq request timeout is mapped to descriptive RuntimeError."""
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()

    timeout_err = groq.APITimeoutError(request=httpx.Request("POST", "https://api.groq.com"))
    mock_client.chat.completions.create = AsyncMock(side_effect=timeout_err)

    provider = GroqLLMProvider(api_key="gsk_test123", client=mock_client)
    with pytest.raises(RuntimeError, match="Groq API request timed out"):
        await provider.generate_structured("prompt", "sys", SamplePlanSchema)


@pytest.mark.asyncio
async def test_groq_not_found_invalid_model_error():
    """Ensure Groq 404 NotFoundError (e.g. invalid model ID) is mapped to descriptive RuntimeError."""
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()

    mock_resp = httpx.Response(404, request=httpx.Request("POST", "https://api.groq.com"))
    not_found_err = groq.NotFoundError("Model non-existent-model does not exist", response=mock_resp, body=None)
    mock_client.chat.completions.create = AsyncMock(side_effect=not_found_err)

    provider = GroqLLMProvider(
        api_key="gsk_test123",
        model_name="non-existent-model",
        client=mock_client,
    )
    with pytest.raises(RuntimeError, match="Groq model not found or invalid"):
        await provider.generate_structured("prompt", "sys", SamplePlanSchema)


def test_get_llm_provider_factory_returns_groq():
    """Ensure factory resolves 'groq' to GroqLLMProvider instance."""
    provider = get_llm_provider("groq", api_key="gsk_factory_test")
    assert isinstance(provider, GroqLLMProvider)
    assert provider.api_key == "gsk_factory_test"
