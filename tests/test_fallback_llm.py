"""
tests/test_fallback_llm.py
--------------------------
Unit tests for GroqLLM and FallbackLLM providers.
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from llm.base import BaseLLM, LLMResponse
from llm.fallback import FallbackLLM
from llm.factory import create_llm, LLMProvider


class SampleSchema(BaseModel):
    summary: str = Field(..., description="Summary string.")
    count: int = Field(..., description="Count integer.")


class MockPrimaryLLM(BaseLLM):
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.calls = 0

    @property
    def model_name(self) -> str:
        return "mock-primary"

    def chat(self, messages, *, temperature=0.0, max_tokens=None):
        self.calls += 1
        if self.should_fail:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return LLMResponse(content="Primary response")

    def structured_chat(self, messages, schema, *, temperature=0.0):
        self.calls += 1
        if self.should_fail:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return schema(summary="Primary structured", count=10)


class MockFallbackLLM(BaseLLM):
    def __init__(self):
        self.calls = 0

    @property
    def model_name(self) -> str:
        return "mock-fallback"

    def chat(self, messages, *, temperature=0.0, max_tokens=None):
        self.calls += 1
        return LLMResponse(content="Fallback response")

    def structured_chat(self, messages, schema, *, temperature=0.0):
        self.calls += 1
        return schema(summary="Fallback structured", count=99)


def test_fallback_primary_success():
    """When primary succeeds, fallback is not called."""
    primary = MockPrimaryLLM(should_fail=False)
    fallback = MockFallbackLLM()
    wrapper = FallbackLLM(primary=primary, fallback=fallback)

    res = wrapper.chat([{"role": "user", "content": "hi"}])
    assert res.content == "Primary response"
    assert primary.calls == 1
    assert fallback.calls == 0

    struct_res = wrapper.structured_chat([{"role": "user", "content": "hi"}], SampleSchema)
    assert struct_res.summary == "Primary structured"
    assert primary.calls == 2
    assert fallback.calls == 0


def test_fallback_triggers_on_primary_failure():
    """When primary fails with rate limit or error, fallback is called seamlessly."""
    primary = MockPrimaryLLM(should_fail=True)
    fallback = MockFallbackLLM()
    wrapper = FallbackLLM(primary=primary, fallback=fallback)

    res = wrapper.chat([{"role": "user", "content": "hi"}])
    assert res.content == "Fallback response"
    assert primary.calls == 1
    assert fallback.calls == 1

    struct_res = wrapper.structured_chat([{"role": "user", "content": "hi"}], SampleSchema)
    assert struct_res.summary == "Fallback structured"
    assert struct_res.count == 99
    assert primary.calls == 2
    assert fallback.calls == 2


def test_fallback_model_name():
    """Composite model name displays primary and fallback models."""
    primary = MockPrimaryLLM()
    fallback = MockFallbackLLM()
    wrapper = FallbackLLM(primary=primary, fallback=fallback)
    assert wrapper.model_name == "mock-primary (fallback: mock-fallback)"
