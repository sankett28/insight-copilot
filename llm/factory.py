"""
llm/factory.py
--------------
Factory function that returns a configured BaseLLM instance.

Centralising provider selection here means application code never imports
provider-specific modules directly — only the abstract interface and this factory.
"""

from __future__ import annotations

import os
from enum import Enum

from llm.base import BaseLLM


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    GEMINI = "gemini"
    # Future providers can be added here without changing agent code.


def create_llm(
    provider: str | LLMProvider | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> BaseLLM:
    """Instantiate and return an LLM provider.

    Args:
        provider: Provider name.  Falls back to the ``LLM_PROVIDER`` env var,
                  then ``LLMProvider.GEMINI``.
        model: Optional model override passed to the provider.
        api_key: Optional API key override passed to the provider.

    Returns:
        A configured :class:`~llm.base.BaseLLM` instance.

    Raises:
        ValueError: If *provider* is not recognised.
    """
    resolved = LLMProvider(
        (provider or os.environ.get("LLM_PROVIDER") or LLMProvider.GEMINI).lower()
    )

    if resolved == LLMProvider.GEMINI:
        from llm.gemini import GeminiLLM  # local import avoids circular deps

        return GeminiLLM(model=model, api_key=api_key)

    raise ValueError(
        f"Unknown LLM provider: '{resolved}'. "
        f"Supported providers: {[p.value for p in LLMProvider]}"
    )
