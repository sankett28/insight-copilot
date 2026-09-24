"""
tests/test_fallback_llm.py
--------------------------
Comprehensive unit tests for GroqLLM, FallbackLLM, and create_llm provider factory.
"""

import os
from unittest.mock import MagicMock, patch
from pydantic import BaseModel, Field, ValidationError

import pytest

from llm.base import BaseLLM, LLMResponse
from llm.fallback import FallbackLLM
from llm.factory import create_llm, LLMProvider
from llm.gemini import GeminiLLM
from llm.groq import GroqLLM


class SampleSchema(BaseModel):
    summary: str = Field(..., description="Summary string.")
    count: int = Field(..., description="Count integer.")


class ConfigurableMockLLM(BaseLLM):
    def __init__(self, model_name_str: str = "mock-provider", exception_to_raise: Exception | None = None):
        self._model_name = model_name_str
        self.exception_to_raise = exception_to_raise
        self.chat_calls = 0
        self.struct_calls = 0

    @property
    def model_name(self) -> str:
        return self._model_name

    def chat(self, messages, *, temperature=0.0, max_tokens=None):
        self.chat_calls += 1
        if self.exception_to_raise:
            raise self.exception_to_raise
        return LLMResponse(content=f"{self._model_name} chat ok")

    def structured_chat(self, messages, schema, *, temperature=0.0):
        self.struct_calls += 1
        if self.exception_to_raise:
            raise self.exception_to_raise
        return schema(summary=f"{self._model_name} struct ok", count=42)


# ---------------------------------------------------------------------------
# Requirement A-H: FallbackLLM Behavior Tests
# ---------------------------------------------------------------------------


def test_A_gemini_success_groq_not_called():
    """A. Gemini success -> Groq not called."""
    gemini = ConfigurableMockLLM("gemini-3.5-flash-lite")
    groq = ConfigurableMockLLM("openai/gpt-oss-120b")
    wrapper = FallbackLLM(primary=gemini, fallback=groq)

    res = wrapper.chat([{"role": "user", "content": "hi"}])
    assert res.content == "gemini-3.5-flash-lite chat ok"
    assert gemini.chat_calls == 1
    assert groq.chat_calls == 0


def test_B_gemini_429_groq_called_once():
    """B. Gemini 429 -> Groq called exactly once."""
    gemini = ConfigurableMockLLM("gemini-3.5-flash-lite", exception_to_raise=RuntimeError("429 RESOURCE_EXHAUSTED"))
    groq = ConfigurableMockLLM("openai/gpt-oss-120b")
    wrapper = FallbackLLM(primary=gemini, fallback=groq)

    res = wrapper.chat([{"role": "user", "content": "hi"}])
    assert res.content == "openai/gpt-oss-120b chat ok"
    assert gemini.chat_calls == 1
    assert groq.chat_calls == 1


def test_C_gemini_503_groq_called_once():
    """C. Gemini 503 -> Groq called exactly once."""
    gemini = ConfigurableMockLLM("gemini-3.5-flash-lite", exception_to_raise=RuntimeError("503 UNAVAILABLE"))
    groq = ConfigurableMockLLM("openai/gpt-oss-120b")
    wrapper = FallbackLLM(primary=gemini, fallback=groq)

    struct_res = wrapper.structured_chat([{"role": "user", "content": "hi"}], SampleSchema)
    assert struct_res.summary == "openai/gpt-oss-120b struct ok"
    assert gemini.struct_calls == 1
    assert groq.struct_calls == 1


def test_D_gemini_connection_failure_groq_called_once():
    """D. Gemini connection failure -> Groq called exactly once."""
    gemini = ConfigurableMockLLM("gemini-3.5-flash-lite", exception_to_raise=ConnectionError("Connection refused by peer"))
    groq = ConfigurableMockLLM("openai/gpt-oss-120b")
    wrapper = FallbackLLM(primary=gemini, fallback=groq)

    res = wrapper.chat([{"role": "user", "content": "hi"}])
    assert res.content == "openai/gpt-oss-120b chat ok"
    assert gemini.chat_calls == 1
    assert groq.chat_calls == 1


def test_E_gemini_schema_validation_error_groq_not_called():
    """E. Gemini schema/validation error -> Groq NOT called (re-raised)."""
    val_err = ValueError("Invalid parameter value for column X")
    gemini = ConfigurableMockLLM("gemini-3.5-flash-lite", exception_to_raise=val_err)
    groq = ConfigurableMockLLM("openai/gpt-oss-120b")
    wrapper = FallbackLLM(primary=gemini, fallback=groq)

    with pytest.raises(ValueError, match="Invalid parameter value"):
        wrapper.structured_chat([{"role": "user", "content": "hi"}], SampleSchema)

    assert gemini.struct_calls == 1
    assert groq.struct_calls == 0


def test_F_gemini_authentication_error_groq_not_called():
    """F. Gemini authentication/configuration error -> Groq NOT called (re-raised)."""
    auth_err = EnvironmentError("Gemini API key not found")
    gemini = ConfigurableMockLLM("gemini-3.5-flash-lite", exception_to_raise=auth_err)
    groq = ConfigurableMockLLM("openai/gpt-oss-120b")
    wrapper = FallbackLLM(primary=gemini, fallback=groq)

    with pytest.raises(EnvironmentError, match="Gemini API key not found"):
        wrapper.chat([{"role": "user", "content": "hi"}])

    assert gemini.chat_calls == 1
    assert groq.chat_calls == 0


def test_G_groq_success_result_returned():
    """G. Groq success -> result returned."""
    gemini = ConfigurableMockLLM("gemini-3.5-flash-lite", exception_to_raise=RuntimeError("500 Internal Error"))
    groq = ConfigurableMockLLM("openai/gpt-oss-120b")
    wrapper = FallbackLLM(primary=gemini, fallback=groq)

    res = wrapper.chat([{"role": "user", "content": "hi"}])
    assert res.content == "openai/gpt-oss-120b chat ok"


def test_H_groq_failure_controlled_error_returned():
    """H. Groq failure -> controlled error returned (not swallowed)."""
    gemini = ConfigurableMockLLM("gemini-3.5-flash-lite", exception_to_raise=RuntimeError("503 Service Unavailable"))
    groq = ConfigurableMockLLM("openai/gpt-oss-120b", exception_to_raise=RuntimeError("Groq 404 Model Not Found"))
    wrapper = FallbackLLM(primary=gemini, fallback=groq)

    with pytest.raises(RuntimeError, match="Groq 404 Model Not Found"):
        wrapper.chat([{"role": "user", "content": "hi"}])

    assert gemini.chat_calls == 1
    assert groq.chat_calls == 1


# ---------------------------------------------------------------------------
# Requirement I-L: Defaults & Overrides
# ---------------------------------------------------------------------------


def test_I_default_groq_model():
    """I. Default Groq model is openai/gpt-oss-120b."""
    groq = GroqLLM(api_key="gsk_test_key")
    assert groq.model_name == "openai/gpt-oss-120b"


def test_J_explicit_groq_model_override():
    """J. Explicit GROQ_MODEL override works."""
    groq = GroqLLM(api_key="gsk_test_key", model="qwen/qwen3.8-27b")
    assert groq.model_name == "qwen/qwen3.8-27b"

    with patch.dict(os.environ, {"GROQ_MODEL": "openai/gpt-oss-20b"}):
        groq_env = GroqLLM(api_key="gsk_test_key")
        assert groq_env.model_name == "openai/gpt-oss-20b"


def test_K_default_gemini_model():
    """K. Default Gemini model is gemini-3.5-flash-lite."""
    with patch.dict(os.environ, {}, clear=True):
        llm = GeminiLLM(api_key="AIzaSy_fake_key")
        assert llm.model_name == "gemini-3.5-flash-lite"


def test_L_explicit_gemini_model_override():
    """L. Explicit GEMINI_MODEL override works."""
    llm = GeminiLLM(api_key="AIzaSy_fake_key", model="gemini-3.5-flash")
    assert llm.model_name == "gemini-3.5-flash"

    with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-3.6-flash"}):
        llm_env = GeminiLLM(api_key="AIzaSy_fake_key")
        assert llm_env.model_name == "gemini-3.6-flash"
