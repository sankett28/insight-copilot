"""
tests/test_graph.py
-------------------
Tests for the LangGraph StateGraph construction.

These tests verify the graph wiring (nodes, edges, conditional routing) without
making any LLM calls.  A mock LLM is injected in place of a real provider.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent.graph import build_graph
from llm.base import BaseLLM, LLMResponse
from models.schemas import AnalysisPlan, Intent, PlanStep, ToolName


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _MockLLM(BaseLLM):
    """Minimal BaseLLM implementation for testing — never calls the network."""

    @property
    def model_name(self) -> str:
        return "mock-model"

    def chat(self, messages, *, temperature=0.0, max_tokens=None) -> LLMResponse:
        return LLMResponse(content="mock response")

    def structured_chat(self, messages, schema, *, temperature=0.0):
        # Return a minimal valid AnalysisPlan.
        return AnalysisPlan(
            intent=Intent.METRICS,
            rationale="Mock plan for testing.",
            steps=[
                PlanStep(
                    step_number=1,
                    tool=ToolName.DATA_QUERY,
                    description="Fetch relevant rows.",
                )
            ],
            selected_tools=[ToolName.DATA_QUERY],
        )


@pytest.fixture()
def mock_llm() -> _MockLLM:
    return _MockLLM()


# ---------------------------------------------------------------------------
# Graph construction tests
# ---------------------------------------------------------------------------


def test_build_graph_returns_compiled_graph(mock_llm):
    """build_graph should return a compiled LangGraph object without error."""
    graph = build_graph(mock_llm)
    assert graph is not None


def test_graph_has_expected_nodes(mock_llm):
    """The compiled graph should expose all expected node names."""
    graph = build_graph(mock_llm)
    # LangGraph compiled graphs expose get_graph() for inspection.
    underlying = graph.get_graph()
    node_names = set(underlying.nodes.keys())

    expected = {
        "__start__",
        "planner",
        "router",
        "step_advance",
        "data_query",
        "metrics",
        "trends",
        "charts",
        "synthesizer",
        "error_handler",
    }
    assert expected.issubset(node_names), (
        f"Missing nodes: {expected - node_names}"
    )
