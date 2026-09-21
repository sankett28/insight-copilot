"""
tests/test_trends.py
---------------------
Unit tests for tools/trends.py with temporal analysis assertions.
"""

import pytest
from agent.state import AgentState
from models.schemas import AnalysisPlan, Intent, PlanStep, ToolName, TrendsRequest
from tools.trends import execute_trends_request, trends_tool_node


def test_1_monthly_revenue():
    """Compute monthly revenue trend for 2024 (12 months)."""
    req = TrendsRequest(metric="Revenue", date_column="Date", granularity="month")
    res = execute_trends_request(req)
    assert len(res) == 12
    assert res[0]["period"] == "2024-01-01"
    assert res[-1]["period"] == "2024-12-01"
    assert "total_revenue" in res[0]


def test_2_monthly_profit():
    """Compute monthly profit trend."""
    req = TrendsRequest(metric="Profit", date_column="Date", granularity="month")
    res = execute_trends_request(req)
    assert len(res) == 12
    assert "total_profit" in res[0]


def test_3_filtering_by_region():
    """Compute monthly revenue filtered by Region='North'."""
    req = TrendsRequest(
        metric="Revenue",
        date_column="Date",
        granularity="month",
        filters={"Region": "North"},
    )
    res = execute_trends_request(req)
    assert len(res) == 12
    assert "total_revenue" in res[0]


def test_4_grouping_by_category():
    """Compute monthly revenue grouped by Category."""
    req = TrendsRequest(
        metric="Revenue",
        date_column="Date",
        granularity="month",
        group_by="Category",
    )
    res = execute_trends_request(req)
    assert len(res) > 12  # Multiple category entries per month
    assert "Category" in res[0]
    assert "period" in res[0]


def test_5_different_granularities():
    """Verify quarter and year granularities."""
    q_req = TrendsRequest(metric="Revenue", date_column="Date", granularity="quarter")
    y_req = TrendsRequest(metric="Revenue", date_column="Date", granularity="year")

    q_res = execute_trends_request(q_req)
    y_res = execute_trends_request(y_req)

    assert len(q_res) == 4   # 4 quarters in 2024
    assert len(y_res) == 1   # 1 year (2024)


def test_6_invalid_metric():
    """Verify Pydantic validation error for invalid metric."""
    with pytest.raises(ValueError, match="Invalid metric 'NonExistent'"):
        TrendsRequest(metric="NonExistent", granularity="month")


def test_7_invalid_date_column():
    """Verify Pydantic validation error for invalid date column."""
    with pytest.raises(ValueError, match="Invalid date_column 'ShipDate'"):
        TrendsRequest(metric="Revenue", date_column="ShipDate", granularity="month")


def test_8_malformed_request_node():
    """trends_tool_node returns ToolResult(success=False) on invalid params."""
    plan = AnalysisPlan(
        intent=Intent.TREND,
        rationale="Invalid trend calculation",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.TRENDS,
                description="Calculate bad trend",
                parameters={"metric": "BadMetric", "granularity": "month"},
            )
        ],
        selected_tools=[ToolName.TRENDS],
    )
    state: AgentState = {
        "query": "Calculate bad trend",
        "plan": plan,
        "current_step": 0,
        "tool_results": [],
    }

    out = trends_tool_node(state)
    results = out.get("tool_results", [])
    assert len(results) == 1
    assert results[0].success is False
    assert "Trends calculation error" in results[0].error
