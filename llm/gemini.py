"""
llm/gemini.py
-------------
Gemini provider implementation of BaseLLM using the modern `google-genai` SDK.

The API key is read from the GEMINI_API_KEY environment variable — never hard-coded.
Structured output uses JSON mode with schema guidance compatible across all Gemini API tiers.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel

from llm.base import BaseLLM, LLMResponse

logger = logging.getLogger(__name__)

# Default model; can be overridden via constructor or GEMINI_MODEL env var.
_DEFAULT_MODEL = "gemini-3.5-flash-lite"


class GeminiLLM(BaseLLM):
    """Google Gemini model provider using the modern `google-genai` SDK."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """Initialise the Gemini provider.

        Args:
            model: Model identifier (e.g. ``"gemini-3.5-flash"``).
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
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        print(f"\n[Gemini LLM] Sending Chat Request (model={self._model_name}, temp={temperature})...")
        logger.info("Sending Gemini Chat Request (%s, temp=%.2f)...", self._model_name, temperature)
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=config,
        )
        text_content = response.text or ""
        print(f"[Gemini LLM] Chat Response Received ({len(text_content)} chars)")
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

        Uses Gemini's JSON mode with schema guidance in system prompt to guarantee
        compatibility with unconstrained dictionary parameters in Developer API mode.
        """
        contents, system_instruction = _build_genai_contents_and_system(messages)

        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        schema_prompt = (
            f"\n\nYou must return a valid JSON object matching this schema:\n{schema_json}"
        )

        if system_instruction:
            system_instruction += schema_prompt
        else:
            system_instruction = schema_prompt.strip()

        config = types.GenerateContentConfig(
            temperature=temperature,
            system_instruction=system_instruction,
            response_mime_type="application/json",
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        print(f"\n[Gemini LLM] Sending Structured Request (model={self._model_name}, schema={schema.__name__})...")
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

        raw_text = response.text or ""
        cleaned_json = _clean_json_string(raw_text)

        print(f"[Gemini LLM] Structured Response Received ({len(cleaned_json)} chars)")
        logger.info("Gemini Structured Response Received (%d chars)", len(cleaned_json))
        try:
            return schema.model_validate_json(cleaned_json)
        except Exception:
            parsed = json.loads(cleaned_json)
            return schema.model_validate(parsed)



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_json_string(raw: str) -> str:
    """Strip markdown code fencing, extract JSON object, and remove trailing commas."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx : end_idx + 1]

    import re
    return re.sub(r",\s*([\]}])", r"\1", text)


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
