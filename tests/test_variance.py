"""
tests/test_variance.py
----------------------
Unit tests for the variance capability.
"""

from models.schemas import AnalysisPlan, Intent, PlanStep, ToolName, VarianceRequest
from tools.variance import execute_variance, variance_tool_node


def test_variance_monthly_revenue():
    """Verify monthly variance returns 12 periods with correct lag delta behavior."""
    req = VarianceRequest(metric="Revenue", granularity="month")
    res = execute_variance(req)
    assert len(res) == 12

    # First month must have None for previous, delta, and pct_change
    assert res[0]["prev_total_revenue"] is None
    assert res[0]["absolute_change"] is None
    assert res[0]["pct_change"] is None

    # Subsequent months have computed deltas
    for i in range(1, len(res)):
        assert res[i]["prev_total_revenue"] == res[i - 1]["total_revenue"]
        expected_diff = round(res[i]["total_revenue"] - res[i]["prev_total_revenue"], 2)
        assert abs(res[i]["absolute_change"] - expected_diff) < 0.05


def test_variance_quarterly_granularity():
    """Verify quarterly granularity produces 4 periods."""
    req = VarianceRequest(metric="Profit", granularity="quarter")
    res = execute_variance(req)
    assert len(res) == 4


def test_variance_with_group_by():
    """Verify variance grouped by category calculates partitioned lag metrics."""
    req = VarianceRequest(metric="Revenue", granularity="month", group_by="Category")
    res = execute_variance(req)
    assert len(res) == 36  # 3 categories * 12 months


def test_variance_tool_node_success():
    """Verify variance node executes and appends ToolResult."""
    plan = AnalysisPlan(
        intent=Intent.TREND,
        rationale="Calculate monthly revenue variance.",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.VARIANCE,
                description="Monthly revenue variance",
                parameters={"metric": "Revenue", "granularity": "month"},
            )
        ],
        selected_tools=[ToolName.VARIANCE],
    )
    state = {"plan": plan, "current_step": 0, "tool_results": []}
    result = variance_tool_node(state)
    trs = result["tool_results"]
    assert len(trs) == 1
    assert trs[0].tool == ToolName.VARIANCE
    assert trs[0].success is True
    assert len(trs[0].data) == 12
