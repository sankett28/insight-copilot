"""
tests/test_tools.py
--------------------
Deterministic unit tests for analytical tools: metrics, trends, data_query, and charts.
Tests MUST NOT require a live Gemini API call.
"""

import pytest
from agent.state import AgentState
from models.schemas import (
    AnalysisPlan,
    ChartRequest,
    DataQueryRequest,
    Intent,
    MetricsRequest,
    PlanStep,
    ToolName,
    ToolResult,
    TrendsRequest,
)
from tools.charts import charts_tool_node, render_chart_from_data
from tools.data_query import data_query_tool_node, execute_data_query_request
from tools.metrics import execute_metrics_request, metrics_tool_node
from tools.trends import execute_trends_request, trends_tool_node


# ---------------------------------------------------------------------------
# Metrics Tool Tests
# ---------------------------------------------------------------------------


def test_metrics_total_revenue():
    """Compute total revenue across the dataset."""
    req = MetricsRequest(metric="Revenue", aggregation="sum")
    res = execute_metrics_request(req)
    assert len(res) == 1
    total_rev = res[0]["sum_revenue"]
    assert total_rev > 20000000.0  # Approx 20.7M


def test_metrics_revenue_by_category():
    """Compute revenue grouped by Category."""
    req = MetricsRequest(metric="Revenue", aggregation="sum", group_by="Category", sort="desc")
    res = execute_metrics_request(req)
    assert len(res) == 3
    categories = [r["Category"] for r in res]
    assert set(categories) == {"Accessories", "Office", "Electronics"}
    # Verify sorted descending
    assert res[0]["sum_revenue"] >= res[1]["sum_revenue"] >= res[2]["sum_revenue"]


def test_metrics_profit_by_region():
    """Compute profit grouped by Region."""
    req = MetricsRequest(metric="Profit", aggregation="sum", group_by="Region", limit=5)
    res = execute_metrics_request(req)
    assert len(res) > 0
    assert "sum_profit" in res[0]


def test_metrics_invalid_column():
    """Verify validation error when metric column is invalid."""
    with pytest.raises(ValueError, match="Invalid metric 'Customer'"):
        MetricsRequest(metric="Customer", aggregation="sum")


def test_metrics_tool_node_execution():
    """Test metrics_tool_node integration with AgentState."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Category revenue comparison",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Sum revenue by category",
                parameters={"metric": "Revenue", "aggregation": "sum", "group_by": "Category"},
            )
        ],
        selected_tools=[ToolName.METRICS],
    )
    state: AgentState = {
        "query": "Which category generated the most revenue?",
        "plan": plan,
        "current_step": 0,
        "tool_results": [],
    }

    out = metrics_tool_node(state)
    results = out.get("tool_results", [])
    assert len(results) == 1
    assert results[0].success is True
    assert len(results[0].data) == 3


# ---------------------------------------------------------------------------
# Trends Tool Tests
# ---------------------------------------------------------------------------


def test_trends_monthly_revenue():
    """Compute monthly revenue trend for 2024."""
    req = TrendsRequest(metric="Revenue", date_column="Date", granularity="month")
    res = execute_trends_request(req)
    assert len(res) == 12  # 12 months in 2024
    periods = [r["period"] for r in res]
    assert periods[0] == "2024-01-01"
    assert periods[-1] == "2024-12-01"


def test_trends_monthly_profit():
    """Compute monthly profit trend."""
    req = TrendsRequest(metric="Profit", date_column="Date", granularity="month")
    res = execute_trends_request(req)
    assert len(res) == 12
    assert "total_profit" in res[0]


def test_trends_invalid_date_column():
    """Verify error on invalid date column."""
    with pytest.raises(ValueError, match="Invalid date_column 'ShipDate'"):
        TrendsRequest(metric="Revenue", date_column="ShipDate", granularity="month")


def test_trends_tool_node_execution():
    """Test trends_tool_node with AgentState."""
    plan = AnalysisPlan(
        intent=Intent.TREND,
        rationale="Monthly revenue trend",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.TRENDS,
                description="Monthly revenue trend for 2024",
                parameters={"metric": "Revenue", "date_column": "Date", "granularity": "month"},
            )
        ],
        selected_tools=[ToolName.TRENDS],
    )
    state: AgentState = {
        "query": "Show monthly revenue",
        "plan": plan,
        "current_step": 0,
        "tool_results": [],
    }

    out = trends_tool_node(state)
    results = out.get("tool_results", [])
    assert len(results) == 1
    assert results[0].success is True
    assert len(results[0].data) == 12


# ---------------------------------------------------------------------------
# Data Query Tool Tests
# ---------------------------------------------------------------------------


def test_data_query_filtered():
    """Execute raw data query filtered by Region."""
    req = DataQueryRequest(
        columns=["Date", "Region", "Product", "Revenue"],
        filters={"Region": "North"},
        limit=10,
    )
    res = execute_data_query_request(req)
    assert len(res) == 10
    for r in res:
        assert r["Region"].lower() == "north"
        assert set(r.keys()) == {"Date", "Region", "Product", "Revenue"}


def test_data_query_limit_cap():
    """Verify limit > 100 raises ValidationError via Pydantic schema."""
    with pytest.raises(ValueError):
        DataQueryRequest(limit=200)

    req = DataQueryRequest(limit=50)
    res = execute_data_query_request(req)
    assert len(res) == 50



# ---------------------------------------------------------------------------
# Charts Tool Tests
# ---------------------------------------------------------------------------


def test_charts_rendering_bar():
    """Render a bar chart from pre-computed tabular metrics."""
    data = [
        {"Category": "Electronics", "sum_revenue": 10000.0},
        {"Category": "Office", "sum_revenue": 5000.0},
    ]
    req = ChartRequest(chart_type="bar", x="Category", y="sum_revenue", title="Category Revenue")
    fig_dict = render_chart_from_data(data, req)
    assert isinstance(fig_dict, dict)
    assert "data" in fig_dict
    assert "layout" in fig_dict


def test_charts_tool_node_multi_step():
    """Test multi-step execution where charts consumes preceding trends output."""
    plan = AnalysisPlan(
        intent=Intent.COMBINED,
        rationale="Monthly trend with chart visualization",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.TRENDS,
                description="Calculate monthly revenue",
                parameters={"metric": "Revenue", "date_column": "Date", "granularity": "month"},
                depends_on=[],
            ),
            PlanStep(
                step_number=2,
                tool=ToolName.CHARTS,
                description="Visualize monthly revenue line chart",
                parameters={"chart_type": "line", "x": "period", "y": "total_revenue"},
                depends_on=[1],
            ),
        ],
        selected_tools=[ToolName.TRENDS, ToolName.CHARTS],
    )

    prev_result = ToolResult(
        tool=ToolName.TRENDS,
        step_number=1,
        success=True,
        data=[
            {"period": "2024-01-01", "total_revenue": 1000.0},
            {"period": "2024-02-01", "total_revenue": 1500.0},
        ],
    )

    state: AgentState = {
        "query": "Show monthly revenue and chart it",
        "plan": plan,
        "current_step": 1,
        "tool_results": [prev_result],
    }

    out = charts_tool_node(state)
    results = out.get("tool_results", [])
    artifacts = out.get("chart_artifacts", [])

    assert len(results) == 2
    assert results[1].success is True
    assert len(artifacts) == 1
    assert isinstance(artifacts[0], dict)

