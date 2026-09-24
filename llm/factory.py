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
    GROQ = "groq"


def create_llm(
    provider: str | LLMProvider | None = None,
    model: str | None = None,
    api_key: str | None = None,
    enable_fallback: bool = True,
) -> BaseLLM:
    """Instantiate and return an LLM provider.

    Args:
        provider: Provider name.  Falls back to the ``LLM_PROVIDER`` env var,
                  then ``LLMProvider.GEMINI``.
        model: Optional model override passed to the provider.
        api_key: Optional API key override passed to the provider.
        enable_fallback: If True and GROQ_API_KEY is present, wraps Gemini in
                         a FallbackLLM provider.

    Returns:
        A configured :class:`~llm.base.BaseLLM` instance.

    Raises:
        ValueError: If *provider* is not recognised.
    """
    resolved_str = (provider or os.environ.get("LLM_PROVIDER") or LLMProvider.GEMINI).lower()
    resolved = LLMProvider(resolved_str)

    if resolved == LLMProvider.GROQ:
        from llm.groq import GroqLLM
        return GroqLLM(model=model, api_key=api_key)

    if resolved == LLMProvider.GEMINI:
        from llm.gemini import GeminiLLM  # local import avoids circular deps
        gemini_instance = GeminiLLM(model=model, api_key=api_key)

        # Automatically attach Groq fallback if GROQ_API_KEY is present in env
        groq_key = os.environ.get("GROQ_API_KEY")
        if enable_fallback and groq_key:
            from llm.fallback import FallbackLLM
            from llm.groq import GroqLLM
            try:
                groq_instance = GroqLLM()
                return FallbackLLM(primary=gemini_instance, fallback=groq_instance)
            except Exception:  # noqa: BLE001
                pass

        return gemini_instance

    raise ValueError(
        f"Unknown LLM provider: '{resolved}'. "
        f"Supported providers: {[p.value for p in LLMProvider]}"
    )


# Alias for backward compatibility
get_llm = create_llm

