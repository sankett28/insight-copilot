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
_DEFAULT_MODEL = "gemini-3.5-flash-lite"


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
        """Send a list of messages to Gemini using ChatSession and return the plain-text reply."""
        generation_config: dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["max_output_tokens"] = max_tokens

        gen_config = genai.types.GenerationConfig(**generation_config)

        if not messages:
            return LLMResponse(content="", raw=None)

        # Convert OpenAI-style messages into history + latest user prompt
        history_contents: list[dict[str, Any]] = []
        last_message = messages[-1]

        for msg in messages[:-1]:
            role = "user" if msg.get("role") in ("user", "system") else "model"
            content = msg.get("content", "")
            history_contents.append({"role": role, "parts": [content]})

        print(f"\n[Gemini LLM] Sending Chat Request ({self._model_name}, temp={temperature})...")
        chat_session = self._client.start_chat(history=history_contents)
        response = chat_session.send_message(
            last_message.get("content", ""),
            generation_config=gen_config,
        )
        print(f"[Gemini LLM] Chat Response Received ({len(response.text)} chars)")
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

        print(f"\n[Gemini LLM] Sending Structured Plan Request ({self._model_name}, schema={schema.__name__})...")
        response = self._client.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(**generation_config),
        )

        raw_json = response.text.strip()
        print(f"[Gemini LLM] Structured Response Received ({len(raw_json)} chars):\n{raw_json}")
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
