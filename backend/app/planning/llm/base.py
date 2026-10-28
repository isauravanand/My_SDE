from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseLLMProvider(ABC):
    """Abstract interface for LLM providers used during planning orchestration."""

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        schema_class: type[T],
    ) -> tuple[T, dict[str, Any]]:
        """
        Generate structured output adhering to `schema_class`.
        Returns a tuple of (parsed_pydantic_instance, model_metadata_dict).
        Raises ValueError or RuntimeError on unrecoverable failures.
        """
        pass
