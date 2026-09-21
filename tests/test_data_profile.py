"""
tests/test_data_profile.py
--------------------------
Unit tests for the data_profile analytical tool.
"""

from models.schemas import (
    CANONICAL_COLUMNS,
    CATEGORICAL_COLUMNS,
    NUMERIC_COLUMNS,
    AnalysisPlan,
    DataProfileRequest,
    Intent,
    PlanStep,
    ToolName,
)
from tools.data_profile import data_profile_tool_node, execute_data_profile


def test_execute_data_profile_returns_dict():
    """Verify execute_data_profile returns a properly structured dictionary."""
    data = execute_data_profile(DataProfileRequest())
    assert isinstance(data, dict)
    assert data["dataset_name"] == "Sales_Dataset_2024"
    assert data["row_count"] == 2000
    assert data["column_count"] == 10


def test_execute_data_profile_date_range():
    """Verify date_range contains min and max ISO date strings."""
    data = execute_data_profile()
    date_range = data["date_range"]
    assert "min" in date_range and "max" in date_range
    assert date_range["min"] == "2024-01-01"
    assert date_range["max"] == "2024-12-31"


def test_execute_data_profile_numeric_summary():
    """Verify all 5 numeric columns are summarized with standard statistics."""
    data = execute_data_profile()
    num_sum = data["numeric_summary"]
    for col in NUMERIC_COLUMNS:
        assert col in num_sum
        stats = num_sum[col]
        assert "min" in stats
        assert "max" in stats
        assert "mean" in stats
        assert "stddev" in stats
        assert isinstance(stats["min"], (int, float))
        assert isinstance(stats["max"], (int, float))


def test_execute_data_profile_categorical_cardinality():
    """Verify distinct count statistics for categorical columns."""
    data = execute_data_profile()
    cat_card = data["categorical_cardinality"]
    for col in CATEGORICAL_COLUMNS:
        assert col in cat_card
        assert isinstance(cat_card[col], int)
        assert cat_card[col] > 0
    assert "Region" in cat_card
    assert "Category" in cat_card


def test_execute_data_profile_null_counts():
    """Verify null counts are checked across all canonical columns."""
    data = execute_data_profile()
    null_counts = data["null_counts"]
    assert len(null_counts) == len(CANONICAL_COLUMNS)
    for col in CANONICAL_COLUMNS:
        assert col in null_counts
        assert isinstance(null_counts[col], int)


def test_execute_data_profile_quality_warnings():
    """Verify data_quality_warnings is a list."""
    data = execute_data_profile()
    warnings = data["data_quality_warnings"]
    assert isinstance(warnings, list)


def test_data_profile_tool_node_success():
    """Verify node successfully executes and appends ToolResult."""
    plan = AnalysisPlan(
        intent=Intent.DATA_QUERY,
        rationale="Profile the dataset.",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.DATA_PROFILE,
                description="Profile dataset",
                parameters={},
            )
        ],
        selected_tools=[ToolName.DATA_PROFILE],
    )
    state = {
        "query": "Give me a dataset profile",
        "plan": plan,
        "current_step": 0,
        "tool_results": [],
    }

    result = data_profile_tool_node(state)
    tool_results = result["tool_results"]
    assert len(tool_results) == 1
    tr = tool_results[0]
    assert tr.tool == ToolName.DATA_PROFILE
    assert tr.success is True
    assert tr.data["row_count"] == 2000
    assert tr.error is None


def test_data_profile_tool_node_out_of_bounds():
    """Verify tool node handles missing plan step gracefully."""
    state = {
        "query": "Profile",
        "plan": None,
        "current_step": 0,
        "tool_results": [],
    }
    result = data_profile_tool_node(state)
    tool_results = result["tool_results"]
    assert len(tool_results) == 1
    assert tool_results[0].success is False
    assert "plan missing" in tool_results[0].error
