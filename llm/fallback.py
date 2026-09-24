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
    """Resilient LLM wrapper that attempts execution via primary, falling back on provider availability error."""

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
        """Attempt chat via primary; fallback if a provider availability failure occurs."""
        try:
            return self._primary.chat(messages, temperature=temperature, max_tokens=max_tokens)
        except Exception as exc:  # noqa: BLE001
            if not _is_availability_error(exc):
                # Application/programming/auth error: do not silently switch providers
                logger.error("[LLM Fallback] Primary provider raised non-availability error: %s. Re-raising.", exc)
                raise
            logger.warning(
                "[LLM Fallback] Primary provider (%s) availability failure: %s. Switching to fallback provider (%s).",
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
        """Attempt structured chat via primary; fallback if a provider availability failure occurs."""
        try:
            return self._primary.structured_chat(messages, schema, temperature=temperature)
        except Exception as exc:  # noqa: BLE001
            if not _is_availability_error(exc):
                # Application/programming/auth error: do not silently switch providers
                logger.error("[LLM Fallback] Primary provider structured_chat raised non-availability error: %s. Re-raising.", exc)
                raise
            logger.warning(
                "[LLM Fallback] Primary provider (%s) structured_chat availability failure: %s. Switching to fallback (%s).",
                self._primary.model_name,
                exc,
                self._fallback.model_name,
            )
            print(
                f"[LLM Fallback] Warning: Primary provider ({self._primary.model_name}) failed ({exc}). "
                f"Switching to fallback ({self._fallback.model_name})."
            )
            return self._fallback.structured_chat(messages, schema, temperature=temperature)


def _is_availability_error(exc: Exception) -> bool:
    """Return True if *exc* represents a provider availability/network failure.

    Triggers fallback for:
      - Rate/quota errors (429, RESOURCE_EXHAUSTED)
      - Service errors (500, 502, 503, 504, UNAVAILABLE)
      - Network / connection / transport / timeout failures

    Does NOT trigger fallback for:
      - Authentication / API key configuration errors (401, 403, EnvironmentError)
      - Request schema / parameter / validation errors (ValidationError, ValueError, TypeError)
      - Programming / application bugs
    """

    from pydantic import ValidationError

    # Connection / Network / Timeout errors are always availability failures
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True

    try:
        import httpx
        if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
            return True
    except ImportError:
        pass

    # Exclude strict application/programming/validation exception classes
    if isinstance(exc, (ValidationError, ValueError, TypeError, KeyError, AttributeError)):
        return False

    msg = str(exc).lower()

    # Exclude explicit authentication and bad request status/errors
    if any(auth_term in msg for auth_term in ("401", "403", "unauthorized", "forbidden", "invalid api key", "400 bad request", "api key not found")):
        return False

    # Check for known availability failure indicators in message
    availability_indicators = (
        "429",
        "500",
        "502",
        "503",
        "504",
        "resource_exhausted",
        "rate_limit",
        "quota",
        "unavailable",
        "overloaded",
        "deadline_exceeded",
        "service unavailable",
        "temporarily unavailable",
        "connection",
        "timeout",
    )
    return any(ind in msg for ind in availability_indicators)
