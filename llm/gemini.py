"""
llm/gemini.py
-------------
Gemini provider implementation of BaseLLM.

Uses the `google-generativeai` SDK.  The API key is read from the
GEMINI_API_KEY environment variable — never hard-coded.

Structured output uses Gemini's response_schema parameter (available in
gemini-1.5-pro and later) to guarantee valid JSON that maps to a Pydantic schema.
"""

from __future__ import annotations

import json
import os
from typing import Any

import google.generativeai as genai
from pydantic import BaseModel

from llm.base import BaseLLM, LLMResponse

# Default model; can be overridden via constructor or GEMINI_MODEL env var.
_DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiLLM(BaseLLM):
    """Google Gemini chat model via the `google-generativeai` SDK."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """Initialise the Gemini provider.

        Args:
            model: Model identifier (e.g. ``"gemini-2.0-flash"``).
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
        genai.configure(api_key=resolved_key)

        self._model_name: str = (
            model or os.environ.get("GEMINI_MODEL") or _DEFAULT_MODEL
        )
        self._client = genai.GenerativeModel(self._model_name)

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
        generation_config: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["max_output_tokens"] = max_tokens

        # Gemini SDK expects a flat prompt string *or* a history list.
        # We convert the OpenAI-style message list to a single prompt here.
        # TODO: Migrate to genai.ChatSession for proper multi-turn when the
        #       conversation history grows large.
        prompt = _messages_to_prompt(messages)
        response = self._client.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(**generation_config),
        )
        return LLMResponse(content=response.text, raw=response)

    def structured_chat(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
        *,
        temperature: float = 0.0,
    ) -> BaseModel:
        """Send messages and parse the reply into *schema*.

        Uses Gemini's JSON mode (response_mime_type="application/json") with
        an inline JSON Schema derived from the Pydantic model.
        """
        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "response_mime_type": "application/json",
        }

        prompt = _messages_to_prompt(messages)
        # Append schema hint so the model knows the expected structure.
        prompt += (
            f"\n\nRespond with valid JSON conforming to this schema:\n"
            f"{json.dumps(schema.model_json_schema(), indent=2)}"
        )

        response = self._client.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(**generation_config),
        )

        raw_json = response.text.strip()
        return schema.model_validate_json(raw_json)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _messages_to_prompt(messages: list[dict[str, str]]) -> str:
    """Convert an OpenAI-style message list to a flat prompt string.

    Format:
        System: <content>
        User: <content>
        Assistant: <content>
    """
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "")
        parts.append(f"{role}: {content}")
    return "\n".join(parts)
