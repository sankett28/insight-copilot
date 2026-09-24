"""
llm/groq.py
-----------
Groq LLM provider implementation using httpx.

Fast, low-latency OpenAI-compatible endpoint hosting models such as
llama-3.3-70b-versatile and llama-3.1-8b-instant.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from llm.base import BaseLLM, LLMResponse

logger = logging.getLogger(__name__)

_DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
_GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


class GroqLLM(BaseLLM):
    """Groq API client supporting text completion and structured JSON output."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """Initialise the Groq provider.

        Args:
            model: Model identifier (e.g. 'llama-3.3-70b-versatile').
                   Falls back to GROQ_MODEL env var, then default.
            api_key: Groq API key.
                     Falls back to GROQ_API_KEY env var.
        """
        self._model = (
            model
            or os.environ.get("GROQ_MODEL")
            or _DEFAULT_GROQ_MODEL
        )
        self._api_key = api_key or os.environ.get("GROQ_API_KEY")

        if not self._api_key:
            raise ValueError(
                "Groq API key is missing. Set GROQ_API_KEY in your environment or pass api_key."
            )

    @property
    def model_name(self) -> str:
        """Return the active model string."""
        return self._model

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send chat completion request to Groq API."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        logger.info("[Groq LLM] Sending Chat Request (model=%s, temp=%.2f)...", self._model, temperature)

        with httpx.Client(timeout=60.0) as client:
            resp = client.post(_GROQ_ENDPOINT, headers=headers, json=payload)

        if resp.status_code != 200:
            err_msg = f"Groq API returned HTTP {resp.status_code}: {resp.text}"
            logger.error("[Groq LLM] Chat request failed: %s", err_msg)
            raise RuntimeError(err_msg)

        data = resp.json()
        content = data["choices"][0]["message"]["content"] or ""
        logger.info("[Groq LLM] Chat Response Received (%d chars)", len(content))
        return LLMResponse(content=content, raw=data)

    def structured_chat(
        self,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
        *,
        temperature: float = 0.0,
    ) -> BaseModel:
        """Send chat request requesting structured JSON output conforming to *schema*."""
        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        system_instruction = (
            "You MUST respond ONLY with a valid JSON object matching this JSON schema:\n\n"
            f"{schema_json}\n\n"
            "Do not include any explanation or markdown formatting outside the JSON."
        )

        formatted_messages = [{"role": "system", "content": system_instruction}]
        for msg in messages:
            if msg.get("role") == "system":
                formatted_messages[0]["content"] += f"\n\n{msg['content']}"
            else:
                formatted_messages.append(msg)

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": formatted_messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        logger.info("[Groq LLM] Sending Structured Request (model=%s, schema=%s)...", self._model, schema.__name__)

        with httpx.Client(timeout=60.0) as client:
            resp = client.post(_GROQ_ENDPOINT, headers=headers, json=payload)

        if resp.status_code != 200:
            err_msg = f"Groq API returned HTTP {resp.status_code}: {resp.text}"
            logger.error("[Groq LLM] Structured request failed: %s", err_msg)
            raise RuntimeError(err_msg)

        data = resp.json()
        raw_content = data["choices"][0]["message"]["content"] or ""
        cleaned_json = _clean_json_string(raw_content)

        try:
            return schema.model_validate_json(cleaned_json)
        except (ValidationError, json.JSONDecodeError):
            parsed = json.loads(cleaned_json)
            return schema.model_validate(parsed)


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

    return re.sub(r",\s*([\]}])", r"\1", text)
