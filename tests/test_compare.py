"""
tests/test_compare.py
---------------------
Unit tests for the compare capability.
"""

from models.schemas import AnalysisPlan, CompareRequest, Intent, PlanStep, ToolName
from tools.compare import compare_tool_node, execute_compare


def test_compare_regions_revenue():
    """Verify comparing North and South revenue returns valid side-by-side metrics."""
    req = CompareRequest(
        metric="Revenue",
        aggregation="sum",
        dimension="Region",
        value_a="North",
        value_b="South",
    )
    res = execute_compare(req)
    assert res["metric"] == "Revenue"
    assert res["dimension"] == "Region"
    assert res["entity_a"]["label"] == "North"
    assert res["entity_b"]["label"] == "South"
    assert isinstance(res["entity_a"]["value"], float)
    assert isinstance(res["entity_b"]["value"], float)
    assert res["absolute_delta"] == round(res["entity_a"]["value"] - res["entity_b"]["value"], 2)
    assert isinstance(res["pct_delta"], float)


def test_compare_categories_profit():
    """Verify comparing Category metrics with average aggregation."""
    req = CompareRequest(
        metric="Profit",
        aggregation="avg",
        dimension="Category",
        value_a="Technology",
        value_b="Furniture",
    )
    res = execute_compare(req)
    assert res["aggregation"] == "avg"
    assert res["entity_a"]["label"] == "Technology"
    assert res["entity_b"]["label"] == "Furniture"


def test_compare_with_filters():
    """Verify comparison with additional category filter."""
    req = CompareRequest(
        metric="Revenue",
        aggregation="sum",
        dimension="Region",
        value_a="East",
        value_b="West",
        filters={"Category": "Electronics"},
    )
    res = execute_compare(req)
    assert res["entity_a"]["value"] > 0
    assert res["entity_b"]["value"] > 0


def test_compare_zero_denominator_pct_delta():
    """Verify zero division guard sets pct_delta to None."""
    req = CompareRequest(
        metric="Revenue",
        aggregation="sum",
        dimension="Region",
        value_a="North",
        value_b="NonexistentRegionXYZ",
    )
    res = execute_compare(req)
    assert res["entity_b"]["value"] == 0.0
    assert res["pct_delta"] is None


def test_compare_tool_node_success():
    """Verify compare_tool_node appends ToolResult on success."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Compare regions.",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.COMPARE,
                description="Compare North and South",
                parameters={
                    "metric": "Revenue",
                    "dimension": "Region",
                    "value_a": "North",
                    "value_b": "South",
                },
            )
        ],
        selected_tools=[ToolName.COMPARE],
    )
    state = {"plan": plan, "current_step": 0, "tool_results": []}
    result = compare_tool_node(state)
    trs = result["tool_results"]
    assert len(trs) == 1
    assert trs[0].tool == ToolName.COMPARE
    assert trs[0].success is True
    assert trs[0].data["entity_a"]["label"] == "North"


def test_compare_tool_node_invalid_params():
    """Verify node returns ToolResult with success=False on invalid parameters."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Invalid compare",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.COMPARE,
                description="Invalid compare",
                parameters={"metric": "InvalidMetricXYZ", "dimension": "Region"},
            )
        ],
        selected_tools=[ToolName.COMPARE],
    )
    state = {"plan": plan, "current_step": 0, "tool_results": []}
    result = compare_tool_node(state)
    trs = result["tool_results"]
    assert len(trs) == 1
    assert trs[0].success is False
    assert "validation" in trs[0].error.lower() or "invalid" in trs[0].error.lower()
