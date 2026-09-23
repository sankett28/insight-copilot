"""
tests/test_metrics.py
----------------------
Unit tests for tools/metrics.py with explicit numerical assertions.
"""

import pytest
from agent.state import AgentState
from models.schemas import AnalysisPlan, Intent, MetricsRequest, PlanStep, ToolName
from tools.metrics import execute_metrics_request, metrics_tool_node


def test_1_total_revenue():
    """Compute total revenue and assert actual numerical value."""
    req = MetricsRequest(metric="Revenue", aggregation="sum")
    res = execute_metrics_request(req)
    assert len(res) == 1
    total_rev = res[0]["sum_revenue"]
    assert pytest.approx(total_rev, rel=1e-2) == 20719567.0


def test_2_revenue_by_region():
    """Compute revenue by region and verify group structure."""
    req = MetricsRequest(metric="Revenue", aggregation="sum", group_by="Region")
    res = execute_metrics_request(req)
    assert len(res) > 0
    assert "Region" in res[0]
    assert "sum_revenue" in res[0]


def test_3_profit_by_category():
    """Compute profit grouped by Category."""
    req = MetricsRequest(metric="Profit", aggregation="sum", group_by="Category", sort="desc")
    res = execute_metrics_request(req)
    assert len(res) == 3
    cats = [r["Category"] for r in res]
    assert set(cats) == {"Accessories", "Office", "Electronics"}
    # Assert descending order
    assert res[0]["sum_profit"] >= res[1]["sum_profit"] >= res[2]["sum_profit"]


def test_4_average_unit_price():
    """Compute average unit price."""
    req = MetricsRequest(metric="Unit_Price", aggregation="average")
    res = execute_metrics_request(req)
    assert len(res) == 1
    avg_price = res[0]["average_unit_price"]
    assert pytest.approx(avg_price, rel=1e-2) == 1062.12



def test_5_min_max_units_sold():
    """Compute MIN and MAX units sold."""
    min_req = MetricsRequest(metric="Units_Sold", aggregation="min")
    max_req = MetricsRequest(metric="Units_Sold", aggregation="max")
    min_res = execute_metrics_request(min_req)
    max_res = execute_metrics_request(max_req)

    assert min_res[0]["min_units_sold"] == -5.0
    assert max_res[0]["max_units_sold"] == 19.0


def test_6_count_records():
    """Compute count of records."""
    req = MetricsRequest(metric="Revenue", aggregation="count")
    res = execute_metrics_request(req)
    assert res[0]["count_revenue"] == 1921  # 2000 total - 79 nulls = 1921 non-nulls


def test_7_filtering():
    """Compute total revenue filtered by Category='Electronics'."""
    req = MetricsRequest(metric="Revenue", aggregation="sum", filters={"Category": "Electronics"})
    res = execute_metrics_request(req)
    assert len(res) == 1
    elec_rev = res[0]["sum_revenue"]
    assert elec_rev > 10000000.0  # Approx 10.4M


def test_8_sorting():
    """Verify asc vs desc sorting on aggregated metric."""
    asc_req = MetricsRequest(metric="Revenue", aggregation="sum", group_by="Category", sort="asc")
    asc_res = execute_metrics_request(asc_req)
    assert asc_res[0]["sum_revenue"] <= asc_res[-1]["sum_revenue"]


def test_9_limit():
    """Verify limit parameter on grouped results."""
    req = MetricsRequest(metric="Revenue", aggregation="sum", group_by="Salesperson", limit=3)
    res = execute_metrics_request(req)
    assert len(res) == 3


def test_10_invalid_metric():
    """Verify Pydantic validation rejects non-existent metric column."""
    with pytest.raises(ValueError, match="Invalid metric 'NonExistent'"):
        MetricsRequest(metric="NonExistent", aggregation="sum")


def test_11_invalid_group_by():
    """Verify runtime error when group_by column is non-canonical."""
    req = MetricsRequest(metric="Revenue", aggregation="sum", group_by="BadGroupCol")
    with pytest.raises(ValueError, match="Invalid group_by column 'BadGroupCol'"):
        execute_metrics_request(req)


def test_12_malformed_request_node():
    """metrics_tool_node returns ToolResult(success=False) on invalid params."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Invalid calculation",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Calculate bad metric",
                parameters={"metric": "BadMetricColumn", "aggregation": "sum"},
            )
        ],
        selected_tools=[ToolName.METRICS],
    )
    state: AgentState = {
        "query": "Calculate bad metric",
        "plan": plan,
        "current_step": 0,
        "tool_results": [],
    }

    out = metrics_tool_node(state)
    results = out.get("tool_results", [])
    assert len(results) == 1
    assert results[0].success is False
    assert "Invalid metric" in results[0].error


def test_13_list_filter_metrics():
    """Verify metrics calculation with list filter e.g. Region in ['West', 'North']."""
    req = MetricsRequest(
        metric="Revenue",
        aggregation="sum",
        filters={"Region": ["West", "North"]},
    )
    res = execute_metrics_request(req)
    assert len(res) == 1
    assert res[0]["sum_revenue"] > 0


def test_14_empty_list_filter_metrics():
    """Verify metrics calculation with empty list filter returns null or NaN sum."""
    import pandas as pd

    req = MetricsRequest(
        metric="Revenue",
        aggregation="sum",
        filters={"Region": []},
    )
    res = execute_metrics_request(req)
    assert len(res) == 1
    val = res[0]["sum_revenue"]
    assert val is None or pd.isna(val) or val == 0.0


