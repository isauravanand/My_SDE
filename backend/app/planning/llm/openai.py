import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.core.config import settings
from app.planning.llm.base import BaseLLMProvider

T = TypeVar("T", bound=BaseModel)


class OpenAILLMProvider(BaseLLMProvider):
    """
    OpenAI-compatible LLM provider implementing structured output generation.
    Supports standard OpenAI endpoint or compatible self-hosted / proxy endpoints.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.model_name = model_name or settings.LLM_MODEL
        self.temperature = (
            temperature if temperature is not None else settings.PLANNING_TEMPERATURE
        )
        self.max_tokens = max_tokens or settings.PLANNING_MAX_OUTPUT_TOKENS

    async def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        schema_class: type[T],
    ) -> tuple[T, dict[str, Any]]:
        if not self.api_key:
            raise ValueError("LLM_API_KEY is not configured for OpenAILLMProvider")

        schema_json = json.dumps(schema_class.model_json_schema())
        augmented_system_prompt = (
            f"{system_prompt}\n\n"
            f"You MUST format your entire response as a valid JSON object strictly matching this JSON Schema:\n"
            f"{schema_json}\n"
            f"Return ONLY valid JSON. Do not include markdown code block backticks or commentary."
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": augmented_system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )

            if response.status_code >= 400:
                raise RuntimeError(
                    f"LLM API request failed with status {response.status_code}: {response.text}"
                )

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})

            # Clean any stray formatting if present
            cleaned_content = content.strip()
            if cleaned_content.startswith("```json"):
                cleaned_content = cleaned_content[7:]
            if cleaned_content.startswith("```"):
                cleaned_content = cleaned_content[3:]
            if cleaned_content.endswith("```"):
                cleaned_content = cleaned_content[:-3]
            cleaned_content = cleaned_content.strip()

            parsed_dict = json.loads(cleaned_content)
            instance = schema_class.model_validate(parsed_dict)

            metadata = {
                "provider": "openai",
                "model": self.model_name,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

            return instance, metadata
