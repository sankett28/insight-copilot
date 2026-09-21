"""
tests/test_anomaly_detection.py
-------------------------------
Unit tests for the anomaly_detection analytical capability.
"""

from models.schemas import (
    AnalysisPlan,
    AnomalyRequest,
    Intent,
    PlanStep,
    ToolName,
)
from tools.anomaly_detection import anomaly_detection_tool_node, execute_anomaly_detection


def test_anomaly_detection_iqr_revenue():
    """Verify IQR anomaly detection on Revenue calculates bounds and returns outliers."""
    req = AnomalyRequest(metric="Revenue", method="iqr", threshold=1.5)
    res = execute_anomaly_detection(req)

    assert res["metric"] == "Revenue"
    assert res["method"] == "iqr"
    assert res["threshold"] == 1.5
    assert "q1" in res and "q3" in res
    assert res["q3"] >= res["q1"]
    assert res["upper_bound"] >= res["q3"]
    assert isinstance(res["anomalies_found"], int)
    assert isinstance(res["rows"], list)

    for row in res["rows"]:
        assert "Revenue" in row
        assert "anomaly_type" in row
        assert row["anomaly_type"] in ("high", "low")
        assert row["Revenue"] > res["upper_bound"] or row["Revenue"] < res["lower_bound"]


def test_anomaly_detection_zscore_profit():
    """Verify Z-score anomaly detection on Profit calculates mean, stddev, and z_scores."""
    req = AnomalyRequest(metric="Profit", method="zscore", threshold=2.5)
    res = execute_anomaly_detection(req)

    assert res["metric"] == "Profit"
    assert res["method"] == "zscore"
    assert "mean" in res and "stddev" in res
    assert isinstance(res["anomalies_found"], int)

    for row in res["rows"]:
        assert "Profit" in row
        assert "z_score" in row
        assert abs(row["z_score"]) >= 2.5


def test_anomaly_detection_with_filter():
    """Verify anomaly detection scoped to a specific region."""
    req = AnomalyRequest(metric="Units_Sold", method="iqr", filters={"Region": "North"})
    res = execute_anomaly_detection(req)
    for row in res["rows"]:
        assert row["Region"].lower() == "north"


def test_anomaly_detection_tool_node_success():
    """Verify tool node execution and ToolResult generation."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Find revenue anomalies",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.ANOMALY_DETECTION,
                description="Detect revenue outliers",
                parameters={"metric": "Revenue", "method": "iqr"},
            )
        ],
        selected_tools=[ToolName.ANOMALY_DETECTION],
    )
    state = {"plan": plan, "current_step": 0, "tool_results": []}
    result = anomaly_detection_tool_node(state)
    trs = result["tool_results"]
    assert len(trs) == 1
    assert trs[0].tool == ToolName.ANOMALY_DETECTION
    assert trs[0].success is True
    assert "anomalies_found" in trs[0].data
