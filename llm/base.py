"""
llm/base.py
-----------
Abstract base class for all LLM providers.

This thin interface decouples the agent nodes from any specific SDK.
Adding a new provider (OpenAI, Anthropic, …) means implementing this
interface — no agent code changes required.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class LLMResponse(BaseModel):
    """Normalised response returned by every provider."""

    content: str
    """Raw text content of the model response."""

    raw: Any = None
    """Optional: the full SDK response object for debugging / token counting."""


class BaseLLM(ABC):
    """Provider-agnostic interface for a chat/completion model."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a list of chat messages and return the model reply.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
            temperature: Sampling temperature (0.0 = deterministic).
            max_tokens: Optional hard cap on output tokens.

        Returns:
            Normalised :class:`LLMResponse`.
        """

    @abstractmethod
    def structured_chat(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
        *,
        temperature: float = 0.0,
    ) -> BaseModel:
        """Send chat messages and parse the response into a Pydantic model.

        The provider is responsible for using function-calling / JSON mode
        to ensure structured output.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
            schema: Pydantic model class to parse the response into.
            temperature: Sampling temperature.

        Returns:
            An instance of *schema*.
        """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable identifier for the model in use."""
