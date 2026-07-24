from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class LLMProvider(ABC):
    """Abstract LLM provider interface.

    Implementations should be lightweight wrappers around HTTP/SDK calls
    and return raw text output. Higher-level services will handle SQL
    extraction/validation/repair.
    """

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        """Send `prompt` to the LLM and return the raw text response."""

    async def close(self) -> None:
        """Optional cleanup hook for async clients."""
        return None
