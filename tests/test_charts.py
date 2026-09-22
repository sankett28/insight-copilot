"""
tests/test_charts.py
---------------------
Unit tests for tools/charts.py (Plotly chart rendering engine).
Tests MUST NOT require Streamlit or live LLM calls.
"""

from agent.state import AgentState
from models.schemas import AnalysisPlan, ChartRequest, Intent, PlanStep, ToolName, ToolResult
from tools.charts import charts_tool_node, render_chart_from_data


def test_1_bar_chart():
    """Render a bar chart from tabular data."""
    data = [
        {"Category": "Electronics", "sum_revenue": 10000.0},
        {"Category": "Office", "sum_revenue": 5000.0},
    ]
    req = ChartRequest(chart_type="bar", x="Category", y="sum_revenue", title="Category Revenue")
    fig_dict = render_chart_from_data(data, req)

    assert isinstance(fig_dict, dict)
    assert "data" in fig_dict
    assert "layout" in fig_dict
    assert fig_dict["data"][0]["type"] == "bar"


def test_2_line_chart():
    """Render a line chart from tabular time-series data."""
    data = [
        {"period": "2024-01-01", "total_revenue": 1000.0},
        {"period": "2024-02-01", "total_revenue": 1500.0},
    ]
    req = ChartRequest(chart_type="line", x="period", y="total_revenue", title="Monthly Revenue")
    fig_dict = render_chart_from_data(data, req)

    assert isinstance(fig_dict, dict)
    assert fig_dict["data"][0]["type"] == "scatter"  # Plotly express line type is scatter mode=lines
    assert fig_dict["data"][0]["mode"] == "lines"


def test_3_scatter_chart():
    """Render a scatter plot."""
    data = [
        {"Unit_Price": 100.0, "Revenue": 1000.0},
        {"Unit_Price": 200.0, "Revenue": 2000.0},
    ]
    req = ChartRequest(chart_type="scatter", x="Unit_Price", y="Revenue", title="Price vs Revenue")
    fig_dict = render_chart_from_data(data, req)

    assert isinstance(fig_dict, dict)
    assert fig_dict["data"][0]["type"] == "scatter"


def test_4_correct_xy_fields():
    """Verify x and y fields are mapped correctly in figure layout."""
    data = [{"Region": "North", "Profit": 500.0}]
    req = ChartRequest(chart_type="bar", x="Region", y="Profit", title="Regional Profit")
    fig_dict = render_chart_from_data(data, req)

    assert fig_dict["layout"]["xaxis"]["title"]["text"] == "Region"
    assert fig_dict["layout"]["yaxis"]["title"]["text"] == "Profit"


def test_5_serialized_figure_non_empty():
    """Verify serialized figure dict contains non-empty layout and data keys."""
    data = [{"Category": "Office", "Revenue": 300.0}]
    req = ChartRequest(chart_type="bar", x="Category", y="Revenue")
    fig_dict = render_chart_from_data(data, req)

    assert len(fig_dict.keys()) > 0
    assert len(fig_dict["data"]) > 0


def test_6_inferred_xy_columns():
    """Verify charts_tool_node infers x and y if parameters are partially missing."""
    plan = AnalysisPlan(
        intent=Intent.CHART,
        rationale="Visualize preceding output",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.CHARTS,
                description="Auto chart",
                parameters={"chart_type": "bar"},
            )
        ],
        selected_tools=[ToolName.CHARTS],
    )
    prev_result = ToolResult(
        tool=ToolName.METRICS,
        step_number=1,
        success=True,
        data=[{"Category": "Electronics", "sum_revenue": 10000.0}],
    )
    state: AgentState = {
        "query": "Visualize revenue",
        "plan": plan,
        "current_step": 0,
        "tool_results": [prev_result],
    }

    out = charts_tool_node(state)
    results = out.get("tool_results", [])
    assert len(results) == 2
    assert results[1].success is True
    assert isinstance(results[1].data, dict)


def test_7_missing_preceding_data_failure():
    """Verify charts_tool_node returns ToolResult(success=False) when no tabular data exists."""
    plan = AnalysisPlan(
        intent=Intent.CHART,
        rationale="Standalone chart without data",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.CHARTS,
                description="Visualize missing data",
            )
        ],
        selected_tools=[ToolName.CHARTS],
    )
    state: AgentState = {
        "query": "Show chart",
        "plan": plan,
        "current_step": 0,
        "tool_results": [],
    }

    out = charts_tool_node(state)
    results = out.get("tool_results", [])
    assert len(results) == 1
    assert results[0].success is False
    assert "No valid preceding tabular data" in results[0].error


def test_8_invalid_axis_column_rejection():
    """Verify render_chart_from_data raises ValueError when axis column is absent from data."""
    import pytest
    data = [{"Region": "North", "Revenue": 1000.0}]
    req = ChartRequest(chart_type="bar", x="NonExistentAxis", y="Revenue")
    with pytest.raises(ValueError, match="not found in data columns"):
        render_chart_from_data(data, req)


def test_9_empty_data_raises_value_error():
    """Verify render_chart_from_data raises ValueError when provided with an empty list."""
    import pytest
    req = ChartRequest(chart_type="bar", x="Region", y="Revenue")
    with pytest.raises(ValueError, match="Cannot render chart from empty data records"):
        render_chart_from_data([], req)
