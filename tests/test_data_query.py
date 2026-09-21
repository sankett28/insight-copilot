"""
tests/test_data_query.py
-------------------------
Unit tests for tools/data_query.py.
"""

import pytest
from agent.state import AgentState
from models.schemas import AnalysisPlan, DataQueryRequest, Intent, PlanStep, ToolName
from tools.data_query import data_query_tool_node, execute_data_query_request


def test_1_valid_column_selection():
    """Select specific known columns."""
    req = DataQueryRequest(columns=["Product", "Revenue"], limit=5)
    res = execute_data_query_request(req)
    assert len(res) == 5
    for r in res:
        assert set(r.keys()) == {"Product", "Revenue"}


def test_2_valid_filter():
    """Filter records by Region='North'."""
    req = DataQueryRequest(filters={"Region": "North"}, limit=10)
    res = execute_data_query_request(req)
    assert len(res) == 10
    for r in res:
        assert r["Region"].lower() == "north"


def test_3_sorting():
    """Sort records by Revenue descending."""
    req = DataQueryRequest(sort_by="Revenue", sort_order="desc", limit=5)
    res = execute_data_query_request(req)
    assert len(res) == 5
    revenues = [r["Revenue"] for r in res]
    assert revenues == sorted(revenues, reverse=True)


def test_4_limit():
    """Enforce specified row limit."""
    req = DataQueryRequest(limit=15)
    res = execute_data_query_request(req)
    assert len(res) == 15


def test_5_multiple_filters():
    """Filter by Region='North' AND Category='Electronics'."""
    req = DataQueryRequest(filters={"Region": "North", "Category": "Electronics"}, limit=10)
    res = execute_data_query_request(req)
    assert len(res) > 0
    for r in res:
        assert r["Region"].lower() == "north"
        assert r["Category"].lower() == "electronics"


def test_6_invalid_column_ignored_safely():
    """Ignore non-canonical columns in column selection and fall back safely."""
    req = DataQueryRequest(columns=["InvalidCol", "Product"], limit=5)
    res = execute_data_query_request(req)
    assert len(res) == 5
    assert "Product" in res[0]


def test_7_invalid_sort_column():
    """Sort by non-existent column ignores sorting safely."""
    req = DataQueryRequest(sort_by="NonExistentColumn", limit=5)
    res = execute_data_query_request(req)
    assert len(res) == 5


def test_8_invalid_limit():
    """Pydantic rejects limit > 100."""
    with pytest.raises(ValueError):
        DataQueryRequest(limit=500)


def test_9_malformed_parameters():
    """data_query_tool_node returns ToolResult(success=False) on malformed parameters."""
    plan = AnalysisPlan(
        intent=Intent.DATA_QUERY,
        rationale="Invalid query",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.DATA_QUERY,
                description="Malformed limit parameter",
                parameters={"limit": "not_an_int"},
            )
        ],
        selected_tools=[ToolName.DATA_QUERY],
    )
    state: AgentState = {
        "query": "Show raw data",
        "plan": plan,
        "current_step": 0,
        "tool_results": [],
    }

    out = data_query_tool_node(state)
    results = out.get("tool_results", [])
    assert len(results) == 1
    assert results[0].success is False
    assert "DataQuery calculation error" in results[0].error


def test_10_tool_result_success():
    """data_query_tool_node returns ToolResult(success=True) on valid step."""
    plan = AnalysisPlan(
        intent=Intent.DATA_QUERY,
        rationale="Valid raw query",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.DATA_QUERY,
                description="Fetch top records",
                parameters={"columns": ["Region", "Revenue"], "limit": 5},
            )
        ],
        selected_tools=[ToolName.DATA_QUERY],
    )
    state: AgentState = {
        "query": "Show top 5 sales",
        "plan": plan,
        "current_step": 0,
        "tool_results": [],
    }

    out = data_query_tool_node(state)
    results = out.get("tool_results", [])
    assert len(results) == 1
    assert results[0].success is True
    assert len(results[0].data) == 5
