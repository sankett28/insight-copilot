"""
tests/test_segmentation.py
---------------------------
Unit tests for the segmentation analytical capability.
"""

from models.schemas import (
    AnalysisPlan,
    Intent,
    PlanStep,
    SegmentationRequest,
    ToolName,
)
from tools.segmentation import execute_segmentation, segmentation_tool_node


def test_segmentation_region_and_category_revenue():
    """Verify 2D cross-segmentation across Region and Category."""
    req = SegmentationRequest(
        metric="Revenue",
        dimension_primary="Region",
        dimension_secondary="Category",
        aggregation="sum",
    )
    res = execute_segmentation(req)

    assert isinstance(res, list)
    assert len(res) > 0
    for row in res:
        assert "Region" in row
        assert "Category" in row
        assert "sum_revenue" in row
        assert isinstance(row["sum_revenue"], (int, float))

    # Verify descending ordering by aggregated metric
    for i in range(len(res) - 1):
        assert res[i]["sum_revenue"] >= res[i + 1]["sum_revenue"]


def test_segmentation_with_limit():
    """Verify limit parameter caps returned cross-segment combinations."""
    req = SegmentationRequest(
        metric="Profit",
        dimension_primary="Salesperson",
        dimension_secondary="Product",
        limit=5,
    )
    res = execute_segmentation(req)
    assert len(res) <= 5


def test_segmentation_tool_node_success():
    """Verify segmentation node execution and state update."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Segment profit by region and category",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.SEGMENTATION,
                description="Cross-segment profit",
                parameters={
                    "metric": "Profit",
                    "dimension_primary": "Region",
                    "dimension_secondary": "Category",
                },
            )
        ],
        selected_tools=[ToolName.SEGMENTATION],
    )
    state = {"plan": plan, "current_step": 0, "tool_results": []}
    result = segmentation_tool_node(state)
    trs = result["tool_results"]
    assert len(trs) == 1
    assert trs[0].tool == ToolName.SEGMENTATION
    assert trs[0].success is True
    assert len(trs[0].data) > 0
