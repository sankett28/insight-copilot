"""
llm/fallback.py
---------------
Fallback LLM provider wrapper.

Wraps a primary LLM provider (e.g. GeminiLLM) and a fallback provider
(e.g. GroqLLM).  If the primary provider raises an exception (such as a 429
quota error or network timeout), the fallback provider is invoked seamlessly.
"""

from __future__ import annotations

import logging
from pydantic import BaseModel

from llm.base import BaseLLM, LLMResponse

logger = logging.getLogger(__name__)


class FallbackLLM(BaseLLM):
    """Resilient LLM wrapper that attempts execution via primary, falling back on error."""

    def __init__(self, primary: BaseLLM, fallback: BaseLLM) -> None:
        """Initialise FallbackLLM with primary and secondary providers."""
        self._primary = primary
        self._fallback = fallback

    @property
    def model_name(self) -> str:
        """Return composite identifier describing primary and fallback models."""
        return f"{self._primary.model_name} (fallback: {self._fallback.model_name})"

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Attempt chat via primary; fallback if an exception occurs."""
        try:
            return self._primary.chat(messages, temperature=temperature, max_tokens=max_tokens)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[LLM Fallback] Primary provider (%s) failed: %s. Switching to fallback provider (%s).",
                self._primary.model_name,
                exc,
                self._fallback.model_name,
            )
            print(
                f"[LLM Fallback] Warning: Primary provider ({self._primary.model_name}) failed ({exc}). "
                f"Switching to fallback ({self._fallback.model_name})."
            )
            return self._fallback.chat(messages, temperature=temperature, max_tokens=max_tokens)

    def structured_chat(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
        *,
        temperature: float = 0.0,
    ) -> BaseModel:
        """Attempt structured chat via primary; fallback if an exception occurs."""
        try:
            return self._primary.structured_chat(messages, schema, temperature=temperature)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[LLM Fallback] Primary provider (%s) structured_chat failed: %s. Switching to fallback (%s).",
                self._primary.model_name,
                exc,
                self._fallback.model_name,
            )
            print(
                f"[LLM Fallback] Warning: Primary provider ({self._primary.model_name}) failed ({exc}). "
                f"Switching to fallback ({self._fallback.model_name})."
            )
            return self._fallback.structured_chat(messages, schema, temperature=temperature)
