"""
llm/gemini.py
-------------
Gemini provider implementation of BaseLLM using the modern `google-genai` SDK.

The API key is read from the GEMINI_API_KEY environment variable — never hard-coded.
Structured output uses Gemini's native response_schema parameter with Pydantic models.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel

from llm.base import BaseLLM, LLMResponse

logger = logging.getLogger(__name__)

# Default model; can be overridden via constructor or GEMINI_MODEL env var.
_DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiLLM(BaseLLM):
    """Google Gemini model provider using the modern `google-genai` SDK."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """Initialise the Gemini provider.

        Args:
            model: Model identifier (e.g. ``"gemini-2.5-flash"``).
                   Falls back to the ``GEMINI_MODEL`` env var, then ``_DEFAULT_MODEL``.
            api_key: Gemini API key.
                     Falls back to the ``GEMINI_API_KEY`` env var.

        Raises:
            EnvironmentError: If no API key is available.
        """
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise EnvironmentError(
                "Gemini API key not found. "
                "Set the GEMINI_API_KEY environment variable or pass api_key=."
            )

        self._model_name: str = (
            model or os.environ.get("GEMINI_MODEL") or _DEFAULT_MODEL
        )
        self._client = genai.Client(api_key=resolved_key)

    # ------------------------------------------------------------------
    # BaseLLM interface
    # ------------------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model_name

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a list of messages to Gemini and return the plain-text reply."""
        if not messages:
            return LLMResponse(content="", raw=None)

        contents, system_instruction = _build_genai_contents_and_system(messages)

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            max_output_tokens=max_tokens,
        )

        logger.info("Sending Gemini Chat Request (%s, temp=%.2f)...", self._model_name, temperature)
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=config,
        )
        text_content = response.text or ""
        logger.info("Gemini Chat Response Received (%d chars)", len(text_content))
        return LLMResponse(content=text_content, raw=response)

    def structured_chat(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
        *,
        temperature: float = 0.0,
    ) -> BaseModel:
        """Send messages and parse the reply into *schema*.

        Uses Gemini's native structured JSON mode with response_schema.
        """
        contents, system_instruction = _build_genai_contents_and_system(messages)

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=schema,
        )

        logger.info(
            "Sending Gemini Structured Request (%s, schema=%s)...",
            self._model_name,
            schema.__name__,
        )
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=config,
        )

        raw_json = (response.text or "").strip()
        logger.info("Gemini Structured Response Received (%d chars)", len(raw_json))
        return schema.model_validate_json(raw_json)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_genai_contents_and_system(
    messages: list[dict[str, str]],
) -> tuple[list[types.Content], str | None]:
    """Convert OpenAI-style message dicts into google-genai Content objects and system instruction."""
    contents: list[types.Content] = []
    system_parts: list[str] = []

    for msg in messages:
        role = msg.get("role", "user")
        content_text = msg.get("content", "")
        if role == "system":
            system_parts.append(content_text)
        else:
            mapped_role = "user" if role == "user" else "model"
            contents.append(
                types.Content(
                    role=mapped_role,
                    parts=[types.Part.from_text(text=content_text)],
                )
            )

    system_instruction = "\n\n".join(system_parts) if system_parts else None
    return contents, system_instruction
