"""
tests/test_tools.py
-------------------
Tests for tool node stubs and their interfaces.

At this skeleton stage:
  - Tool nodes should return ToolResult with success=False and a descriptive error.
  - Public interface functions (run_data_query, compute_metric, etc.) should
    raise NotImplementedError — they are not yet implemented.
"""

from __future__ import annotations

import pytest

from agent.state import AgentState
from models.schemas import ToolName, ToolResult
from tools.charts import charts_tool_node, render_chart, ChartType
from tools.data_query import data_query_tool_node, run_data_query
from tools.metrics import metrics_tool_node, compute_metric, AggregationType
from tools.trends import trends_tool_node, compute_trend, TrendType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_state(step: int = 0) -> AgentState:
    return {
        "messages": [],
        "query": "test",
        "intent": "metrics",
        "plan": None,
        "selected_tools": [],
        "current_step": step,
        "tool_results": [],
        "chart_artifacts": [],
        "final_answer": None,
        "errors": [],
    }


def _extract_result(output: dict) -> ToolResult:
    results = output.get("tool_results", [])
    assert len(results) == 1, f"Expected 1 ToolResult, got {len(results)}"
    return results[0]


# ---------------------------------------------------------------------------
# data_query
# ---------------------------------------------------------------------------


def test_data_query_node_returns_tool_result():
    state = _minimal_state(step=0)
    output = data_query_tool_node(state)
    result = _extract_result(output)
    assert isinstance(result, ToolResult)
    assert result.tool == ToolName.DATA_QUERY
    assert result.step_number == 1


def test_data_query_node_is_stub():
    """Stub should report success=False until implemented."""
    state = _minimal_state(step=0)
    output = data_query_tool_node(state)
    result = _extract_result(output)
    assert result.success is False
    assert result.error is not None


def test_run_data_query_not_implemented():
    with pytest.raises(NotImplementedError):
        run_data_query("dataset")


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


def test_metrics_node_returns_tool_result():
    state = _minimal_state(step=1)
    output = metrics_tool_node(state)
    result = _extract_result(output)
    assert isinstance(result, ToolResult)
    assert result.tool == ToolName.METRICS
    assert result.step_number == 2


def test_metrics_node_is_stub():
    state = _minimal_state()
    output = metrics_tool_node(state)
    result = _extract_result(output)
    assert result.success is False


def test_compute_metric_not_implemented():
    with pytest.raises(NotImplementedError):
        compute_metric("dataset", "sales", AggregationType.SUM)


# ---------------------------------------------------------------------------
# trends
# ---------------------------------------------------------------------------


def test_trends_node_returns_tool_result():
    state = _minimal_state(step=2)
    output = trends_tool_node(state)
    result = _extract_result(output)
    assert isinstance(result, ToolResult)
    assert result.tool == ToolName.TRENDS
    assert result.step_number == 3


def test_trends_node_is_stub():
    state = _minimal_state()
    output = trends_tool_node(state)
    result = _extract_result(output)
    assert result.success is False


def test_compute_trend_not_implemented():
    with pytest.raises(NotImplementedError):
        compute_trend("dataset", "sales", "date")


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------


def test_charts_node_returns_tool_result():
    state = _minimal_state(step=3)
    output = charts_tool_node(state)
    result = _extract_result(output)
    assert isinstance(result, ToolResult)
    assert result.tool == ToolName.CHARTS
    assert result.step_number == 4


def test_charts_node_is_stub():
    state = _minimal_state()
    output = charts_tool_node(state)
    result = _extract_result(output)
    assert result.success is False


def test_render_chart_not_implemented():
    with pytest.raises(NotImplementedError):
        render_chart([], ChartType.BAR, "x", "y")


# ---------------------------------------------------------------------------
# Enum sanity checks
# ---------------------------------------------------------------------------


def test_tool_name_enum_values():
    assert ToolName.DATA_QUERY.value == "data_query"
    assert ToolName.METRICS.value == "metrics"
    assert ToolName.TRENDS.value == "trends"
    assert ToolName.CHARTS.value == "charts"


def test_aggregation_type_enum_values():
    assert AggregationType.SUM.value == "sum"
    assert AggregationType.AVG.value == "avg"


def test_chart_type_enum_values():
    assert ChartType.BAR.value == "bar"
    assert ChartType.LINE.value == "line"
