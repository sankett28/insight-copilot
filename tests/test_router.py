"""
tests/test_router.py
--------------------
Tests for the router_node conditional-edge function and advance_step node.

The router is pure Python (no LLM), so tests are fast and deterministic.
"""

from __future__ import annotations

import pytest

from agent.router import ERROR_NODE, SYNTHESIZER_NODE, advance_step, router_node
from agent.state import AgentState
from models.schemas import ToolName


# ---------------------------------------------------------------------------
# router_node tests
# ---------------------------------------------------------------------------


def _make_state(**kwargs) -> AgentState:
    """Build a minimal AgentState dict for testing."""
    defaults: AgentState = {
        "messages": [],
        "query": "test query",
        "intent": "metrics",
        "plan": None,
        "selected_tools": [],
        "current_step": 0,
        "tool_results": [],
        "chart_artifacts": [],
        "final_answer": None,
        "errors": [],
    }
    defaults.update(kwargs)
    return defaults


def test_router_no_tools_goes_to_synthesizer():
    """With no tools selected, the router should route to the synthesizer."""
    state = _make_state(selected_tools=[], current_step=0)
    assert router_node(state) == SYNTHESIZER_NODE


def test_router_all_steps_done_goes_to_synthesizer():
    """When current_step >= len(selected_tools), route to synthesizer."""
    state = _make_state(
        selected_tools=[ToolName.DATA_QUERY, ToolName.METRICS],
        current_step=2,  # past the end
    )
    assert router_node(state) == SYNTHESIZER_NODE


def test_router_first_step_data_query():
    """First step with DATA_QUERY should route to 'data_query'."""
    state = _make_state(
        selected_tools=[ToolName.DATA_QUERY],
        current_step=0,
    )
    assert router_node(state) == "data_query"


def test_router_first_step_metrics():
    state = _make_state(selected_tools=[ToolName.METRICS], current_step=0)
    assert router_node(state) == "metrics"


def test_router_first_step_trends():
    state = _make_state(selected_tools=[ToolName.TRENDS], current_step=0)
    assert router_node(state) == "trends"


def test_router_first_step_charts():
    state = _make_state(selected_tools=[ToolName.CHARTS], current_step=0)
    assert router_node(state) == "charts"


def test_router_multi_step_routing():
    """In a 3-step plan, the router should select the correct tool at each step."""
    tools = [ToolName.DATA_QUERY, ToolName.TRENDS, ToolName.CHARTS]
    expected = ["data_query", "trends", "charts"]

    for step, expected_node in enumerate(expected):
        state = _make_state(selected_tools=tools, current_step=step)
        assert router_node(state) == expected_node, (
            f"Step {step}: expected '{expected_node}'"
        )


def test_router_errors_go_to_error_handler():
    """When errors are present, the router should route to error_handler."""
    state = _make_state(
        selected_tools=[ToolName.METRICS],
        current_step=0,
        errors=["Something went wrong."],
    )
    assert router_node(state) == ERROR_NODE


# ---------------------------------------------------------------------------
# advance_step tests
# ---------------------------------------------------------------------------


def test_advance_step_increments():
    """advance_step should increment current_step by 1."""
    state = _make_state(current_step=0)
    result = advance_step(state)
    assert result == {"current_step": 1}


def test_advance_step_from_arbitrary_value():
    state = _make_state(current_step=3)
    result = advance_step(state)
    assert result == {"current_step": 4}
