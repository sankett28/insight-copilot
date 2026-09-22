"""
tests/test_profitability.py
--------------------------
Unit tests for the profitability capability.
"""

from models.schemas import AnalysisPlan, Intent, PlanStep, ProfitabilityRequest, ToolName
from tools.profitability import execute_profitability, profitability_tool_node


def test_profitability_categories():
    """Verify category profitability calculates margin accurately."""
    req = ProfitabilityRequest(dimension="Category")
    res = execute_profitability(req)
    assert len(res) == 3
    for row in res:
        assert "Category" in row
        assert "sum_revenue" in row
        assert "sum_cost" in row
        assert "sum_profit" in row
        assert "profit_margin_pct" in row
        expected_margin = round((row["sum_profit"] / row["sum_revenue"]) * 100.0, 2)
        assert abs(row["profit_margin_pct"] - expected_margin) < 0.05


def test_profitability_sorting_by_margin():
    """Verify results are sorted by profit_margin_pct descending."""
    req = ProfitabilityRequest(dimension="Product", sort_by="profit_margin_pct", limit=10)
    res = execute_profitability(req)
    assert len(res) <= 10
    for i in range(len(res) - 1):
        if res[i]["profit_margin_pct"] is not None and res[i + 1]["profit_margin_pct"] is not None:
            assert res[i]["profit_margin_pct"] >= res[i + 1]["profit_margin_pct"]


def test_profitability_sorting_by_revenue():
    """Verify sorting by Revenue orders by sum_revenue."""
    req = ProfitabilityRequest(dimension="Category", sort_by="Revenue")
    res = execute_profitability(req)
    for i in range(len(res) - 1):
        assert res[i]["sum_revenue"] >= res[i + 1]["sum_revenue"]


def test_profitability_tool_node_success():
    """Verify profitability node executes and appends ToolResult with provenance."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Calculate product profitability.",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.PROFITABILITY,
                description="Product profitability",
                parameters={"dimension": "Category"},
            )
        ],
        selected_tools=[ToolName.PROFITABILITY],
    )
    state = {"plan": plan, "current_step": 0, "tool_results": []}
    result = profitability_tool_node(state)
    trs = result["tool_results"]
    assert len(trs) == 1
    assert trs[0].tool == ToolName.PROFITABILITY
    assert trs[0].success is True
    assert len(trs[0].data) == 3
    assert trs[0].source_view == "dataset"
    assert trs[0].row_count == 3
    assert trs[0].execution_time_ms is not None


def test_profitability_zero_matching_records_guard():
    """Verify profitability executes cleanly when filters match 0 rows without division errors."""
    req = ProfitabilityRequest(dimension="Region", filters={"Region": "NonExistentRegion"})
    res = execute_profitability(req)
    assert isinstance(res, list)
    assert len(res) == 0
