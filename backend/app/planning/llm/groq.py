import json
import logging
from typing import Any, TypeVar

import groq
from groq import AsyncGroq
from pydantic import BaseModel

from app.core.config import settings
from app.planning.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class GroqLLMProvider(BaseLLMProvider):
    """
    Groq LLM provider utilizing ultra-fast LPU inference via the official Groq SDK.
    Supports structured JSON schema generation and raw text generation.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float = 60.0,
        client: AsyncGroq | None = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = base_url or settings.LLM_BASE_URL
        if self.base_url:
            self.base_url = self.base_url.rstrip("/")

        # If model is not explicitly provided or is default OpenAI/Claude model, select Groq default
        cfg_model = settings.LLM_MODEL
        if model_name:
            self.model_name = model_name
        elif cfg_model and not cfg_model.startswith("gpt-") and not cfg_model.startswith("claude-"):
            self.model_name = cfg_model
        else:
            self.model_name = DEFAULT_GROQ_MODEL

        self.temperature = (
            temperature if temperature is not None else settings.PLANNING_TEMPERATURE
        )
        self.max_tokens = max_tokens or settings.PLANNING_MAX_OUTPUT_TOKENS
        self.timeout = timeout
        self._client = client

    @property
    def client(self) -> AsyncGroq:
        if self._client is None:
            if not self.api_key:
                raise ValueError("LLM_API_KEY is not configured for GroqLLMProvider")
            kwargs: dict[str, Any] = {
                "api_key": self.api_key,
                "timeout": self.timeout,
            }
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = AsyncGroq(**kwargs)
        return self._client

    async def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        schema_class: type[T],
    ) -> tuple[T, dict[str, Any]]:
        """
        Generates structured output validated against the provided Pydantic schema class.
        """
        if not self.api_key and self._client is None:
            raise ValueError("LLM_API_KEY is not configured for GroqLLMProvider")

        schema_json = json.dumps(schema_class.model_json_schema())
        augmented_system_prompt = (
            f"{system_prompt}\n\n"
            f"You MUST format your entire response as a valid JSON object strictly matching this JSON Schema:\n"
            f"{schema_json}\n"
            f"Return ONLY valid JSON. Do not include markdown code block backticks or commentary."
        )

        messages = [
            {"role": "system", "content": augmented_system_prompt},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
            )
        except groq.AuthenticationError as exc:
            logger.error("Groq authentication failed: %s", exc)
            raise RuntimeError(f"Groq authentication failed (401): {exc.message}") from exc
        except groq.RateLimitError as exc:
            logger.warning("Groq rate limit encountered: %s", exc)
            raise RuntimeError(f"Groq rate limit exceeded (429): {exc.message}") from exc
        except groq.APITimeoutError as exc:
            logger.error("Groq request timed out: %s", exc)
            raise RuntimeError("Groq API request timed out.") from exc
        except groq.NotFoundError as exc:
            logger.error("Groq model not found (%s): %s", self.model_name, exc)
            raise RuntimeError(
                f"Groq model not found or invalid ({self.model_name}): {exc.message}"
            ) from exc
        except groq.BadRequestError as exc:
            logger.error("Groq bad request: %s", exc)
            raise RuntimeError(f"Groq bad request (400): {exc.message}") from exc
        except groq.APIConnectionError as exc:
            logger.error("Groq connection error: %s", exc)
            raise RuntimeError(f"Groq connection error: {exc}") from exc
        except groq.APIStatusError as exc:
            logger.error("Groq API status error (%s): %s", exc.status_code, exc)
            raise RuntimeError(f"Groq API error (status {exc.status_code}): {exc.message}") from exc
        except groq.GroqError as exc:
            logger.error("Groq error: %s", exc)
            raise RuntimeError(f"Groq error: {exc}") from exc

        choice = response.choices[0]
        content = choice.message.content or ""
        usage = getattr(response, "usage", None)

        cleaned_content = self._clean_json_content(content)
        try:
            parsed_dict = json.loads(cleaned_content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Groq model '{self.model_name}' did not return valid JSON: {exc}. "
                f"Raw preview: {cleaned_content[:200]}"
            ) from exc

        # Sanitize evidence references and steps if this is an ImplementationPlan-like payload
        if isinstance(parsed_dict, dict) and "implementation_steps" in parsed_dict:
            ev_list = parsed_dict.get("evidence") or []
            valid_ids = {e.get("evidence_id") for e in ev_list if isinstance(e, dict) and e.get("evidence_id")}
            steps = parsed_dict.get("implementation_steps") or []
            valid_step_ids = {s.get("step_id") for s in steps if isinstance(s, dict) and s.get("step_id")}
            for s in steps:
                if isinstance(s, dict):
                    if "evidence_refs" in s and isinstance(s["evidence_refs"], list):
                        cleaned_refs = [r for r in s["evidence_refs"] if r in valid_ids]
                        if not cleaned_refs and s.get("location_status") == "verified_existing":
                            if valid_ids:
                                cleaned_refs = [sorted(valid_ids)[0]]
                            else:
                                s["location_status"] = "proposed_new"
                        s["evidence_refs"] = cleaned_refs
                    if "dependencies" in s and isinstance(s["dependencies"], list):
                        s["dependencies"] = [d for d in s["dependencies"] if d in valid_step_ids]

        try:
            instance = schema_class.model_validate(parsed_dict)
        except Exception as exc:
            raise ValueError(
                f"Groq structured output does not satisfy schema '{schema_class.__name__}': {exc}"
            ) from exc

        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        total_tokens = (
            getattr(usage, "total_tokens", 0)
            if usage
            else (prompt_tokens + completion_tokens)
        )

        metadata = {
            "provider": "groq",
            "model": self.model_name,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

        return instance, metadata

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str,
    ) -> tuple[str, dict[str, Any]]:
        """
        Generates raw text response (e.g. for patch diff generation).
        """
        if not self.api_key and self._client is None:
            raise ValueError("LLM_API_KEY is not configured for GroqLLMProvider")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        effective_max_tokens = max(self.max_tokens, 16384)
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=self.temperature,
                max_tokens=effective_max_tokens,
            )
        except groq.AuthenticationError as exc:
            logger.error("Groq authentication failed: %s", exc)
            raise RuntimeError(f"Groq authentication failed (401): {exc.message}") from exc
        except groq.RateLimitError as exc:
            logger.warning("Groq rate limit encountered: %s", exc)
            raise RuntimeError(f"Groq rate limit exceeded (429): {exc.message}") from exc
        except groq.APITimeoutError as exc:
            logger.error("Groq request timed out: %s", exc)
            raise RuntimeError("Groq API request timed out.") from exc
        except groq.NotFoundError as exc:
            logger.error("Groq model not found (%s): %s", self.model_name, exc)
            raise RuntimeError(
                f"Groq model not found or invalid ({self.model_name}): {exc.message}"
            ) from exc
        except groq.BadRequestError as exc:
            logger.error("Groq bad request: %s", exc)
            raise RuntimeError(f"Groq bad request (400): {exc.message}") from exc
        except groq.APIConnectionError as exc:
            logger.error("Groq connection error: %s", exc)
            raise RuntimeError(f"Groq connection error: {exc}") from exc
        except groq.APIStatusError as exc:
            logger.error("Groq API status error (%s): %s", exc.status_code, exc)
            raise RuntimeError(f"Groq API error (status {exc.status_code}): {exc.message}") from exc
        except groq.GroqError as exc:
            logger.error("Groq error: %s", exc)
            raise RuntimeError(f"Groq error: {exc}") from exc

        choice = response.choices[0]
        if choice.finish_reason == "length":
            logger.error("Groq text generation was truncated due to token limit (finish_reason=length).")
            raise RuntimeError(
                "LLM text generation output was truncated due to output token limits. Please retry with a more focused plan or higher token allowance."
            )
        content = choice.message.content or ""
        usage = getattr(response, "usage", None)

        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        total_tokens = (
            getattr(usage, "total_tokens", 0)
            if usage
            else (prompt_tokens + completion_tokens)
        )

        metadata = {
            "provider": "groq",
            "model": self.model_name,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

        return content, metadata

    @staticmethod
    def _clean_json_content(content: str) -> str:
        """Strips markdown code block fences and surrounding whitespace."""
        cleaned = content.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return cleaned.strip()
