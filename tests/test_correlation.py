"""
tests/test_correlation.py
-------------------------
Unit tests for the correlation analytical capability.
"""

from models.schemas import (
    AnalysisPlan,
    CorrelationRequest,
    Intent,
    PlanStep,
    ToolName,
)
from tools.correlation import correlation_tool_node, execute_correlation


def test_correlation_units_sold_and_revenue():
    """Verify Pearson correlation between Units_Sold and Revenue is strongly positive."""
    req = CorrelationRequest(field_a="Units_Sold", field_b="Revenue")
    res = execute_correlation(req)

    assert res["field_a"] == "Units_Sold"
    assert res["field_b"] == "Revenue"
    assert isinstance(res["correlation_coefficient"], float)
    assert -1.0 <= res["correlation_coefficient"] <= 1.0
    assert res["correlation_coefficient"] > 0.5  # Units sold strongly drives revenue
    assert res["sample_size"] > 1800
    assert "interpretation" in res
    assert "caveat" in res
    assert "does not imply causation" in res["caveat"].lower()


def test_correlation_revenue_and_cost():
    """Verify Revenue and Cost correlation is calculated with sample size."""
    req = CorrelationRequest(field_a="Revenue", field_b="Cost")
    res = execute_correlation(req)
    assert res["correlation_coefficient"] > 0.0
    assert res["sample_size"] > 0


def test_correlation_with_filter():
    """Verify correlation calculation with dimension filter applied."""
    req = CorrelationRequest(
        field_a="Revenue",
        field_b="Profit",
        filters={"Region": "West"},
    )
    res = execute_correlation(req)
    assert isinstance(res["correlation_coefficient"], float)
    assert res["sample_size"] > 0


def test_correlation_tool_node_success():
    """Verify correlation node execution."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Compute units to revenue correlation",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.CORRELATION,
                description="Correlation calculation",
                parameters={"field_a": "Units_Sold", "field_b": "Revenue"},
            )
        ],
        selected_tools=[ToolName.CORRELATION],
    )
    state = {"plan": plan, "current_step": 0, "tool_results": []}
    result = correlation_tool_node(state)
    trs = result["tool_results"]
    assert len(trs) == 1
    assert trs[0].tool == ToolName.CORRELATION
    assert trs[0].success is True
    assert "correlation_coefficient" in trs[0].data
