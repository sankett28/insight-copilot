"""
tests/test_contribution.py
-------------------------
Unit tests for the contribution capability.
"""

from models.schemas import AnalysisPlan, ContributionRequest, Intent, PlanStep, ToolName
from tools.contribution import contribution_tool_node, execute_contribution


def test_contribution_categories_revenue():
    """Verify category contribution to total revenue sums to ~100%."""
    req = ContributionRequest(metric="Revenue", dimension="Category")
    res = execute_contribution(req)
    assert isinstance(res, list)
    assert len(res) == 3
    for row in res:
        assert "Category" in row
        assert "sum_revenue" in row
        assert "pct_of_total" in row
        assert row["pct_of_total"] > 0
    total_pct = sum(r["pct_of_total"] for r in res)
    assert abs(total_pct - 100.0) < 0.1


def test_contribution_ordered_descending():
    """Verify contribution rows are sorted descending by metric value."""
    req = ContributionRequest(metric="Profit", dimension="Category")
    res = execute_contribution(req)
    for i in range(len(res) - 1):
        assert res[i]["sum_profit"] >= res[i + 1]["sum_profit"]
        assert res[i]["pct_of_total"] >= res[i + 1]["pct_of_total"]


def test_contribution_with_limit():
    """Verify limit parameter caps the returned rows."""
    req = ContributionRequest(metric="Revenue", dimension="Product", limit=5)
    res = execute_contribution(req)
    assert len(res) <= 5


def test_contribution_tool_node_success():
    """Verify node successfully executes and appends ToolResult with provenance."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Category contribution to profit.",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.CONTRIBUTION,
                description="Category breakdown",
                parameters={"metric": "Profit", "dimension": "Category"},
            )
        ],
        selected_tools=[ToolName.CONTRIBUTION],
    )
    state = {"plan": plan, "current_step": 0, "tool_results": []}
    result = contribution_tool_node(state)
    trs = result["tool_results"]
    assert len(trs) == 1
    assert trs[0].tool == ToolName.CONTRIBUTION
    assert trs[0].success is True
    assert len(trs[0].data) == 3
    assert trs[0].source_view == "dataset"
    assert trs[0].row_count == 3
    assert trs[0].execution_time_ms is not None


def test_contribution_preserves_population_share_with_limit():
    """Verify pct_of_total is calculated over the full population even when limit is applied."""
    req_full = ContributionRequest(metric="Revenue", dimension="Product")
    res_full = execute_contribution(req_full)

    req_limit = ContributionRequest(metric="Revenue", dimension="Product", limit=3)
    res_limit = execute_contribution(req_limit)

    assert len(res_limit) == 3
    for i in range(3):
        assert res_limit[i]["Product"] == res_full[i]["Product"]
        assert res_limit[i]["pct_of_total"] == res_full[i]["pct_of_total"]
