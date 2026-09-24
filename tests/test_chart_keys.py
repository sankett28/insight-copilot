"""Unit tests for deterministic Plotly chart element key generation and artifact identity."""

import pytest
from utils.ui_helpers import generate_chart_key, is_plotly_figure_dict
from models.schemas import ChartRequest, ToolName, ToolResult, PlanStep, AnalysisPlan, Intent
from tools.charts import charts_tool_node, render_chart_from_data
from agent.state import AgentState


def test_generate_chart_key_determinism():
    """Verify generate_chart_key produces identical keys given identical inputs across reruns."""
    key1 = generate_chart_key(run_id="run-123", turn_idx=1, step_num=2, chart_idx=0, context="chat_history")
    key2 = generate_chart_key(run_id="run-123", turn_idx=1, step_num=2, chart_idx=0, context="chat_history")
    assert key1 == key2
    assert key1 == "chart_chat_history_run_123_step_2_idx_0"


def test_generate_chart_key_uniqueness_across_contexts():
    """Verify distinct keys for different UI rendering contexts (chat vs live stream vs inspector)."""
    k_chat = generate_chart_key(run_id="run-123", turn_idx=1, step_num=2, chart_idx=0, context="chat_history")
    k_stream = generate_chart_key(run_id="run-123", turn_idx=1, step_num=2, chart_idx=0, context="live_stream")
    k_inspector = generate_chart_key(run_id="run-123", turn_idx=1, step_num=2, chart_idx=0, context="inspector_tool")

    assert len({k_chat, k_stream, k_inspector}) == 3
    assert "chat_history" in k_chat
    assert "live_stream" in k_stream
    assert "inspector_tool" in k_inspector


def test_generate_chart_key_uniqueness_across_steps_and_charts():
    """Verify distinct keys when multiple charts are produced in a single response or turn."""
    k_step2_chart0 = generate_chart_key(run_id="run-1", turn_idx=1, step_num=2, chart_idx=0, context="chat_history")
    k_step2_chart1 = generate_chart_key(run_id="run-1", turn_idx=1, step_num=2, chart_idx=1, context="chat_history")
    k_step4_chart0 = generate_chart_key(run_id="run-1", turn_idx=1, step_num=4, chart_idx=0, context="chat_history")

    assert len({k_step2_chart0, k_step2_chart1, k_step4_chart0}) == 3


def test_generate_chart_key_uniqueness_across_runs():
    """Verify identical queries across different turns/runs get distinct keys."""
    k_run1 = generate_chart_key(run_id="run-100", turn_idx=1, step_num=2, chart_idx=0, context="chat_history")
    k_run2 = generate_chart_key(run_id="run-200", turn_idx=3, step_num=2, chart_idx=0, context="chat_history")
    assert k_run1 != k_run2


def test_is_plotly_figure_dict():
    """Verify detection of Plotly figure dictionaries."""
    valid_fig_dict = {"data": [{"type": "bar", "x": ["North", "South"], "y": [100, 200]}], "layout": {"title": "Revenue"}}
    assert is_plotly_figure_dict(valid_fig_dict) is True

    # Invalid dictionaries
    assert is_plotly_figure_dict({"data": "not a list", "layout": {}}) is False
    assert is_plotly_figure_dict({"numeric_summary": {}, "row_count": 10}) is False
    assert is_plotly_figure_dict(None) is False
    assert is_plotly_figure_dict([]) is False


def test_charts_tool_node_attaches_stable_metadata():
    """Verify charts_tool_node sets _chart_id, _step_number, and _run_id on figure dict."""
    state = AgentState(
        run_id="test_run_uuid",
        current_step=0,
        plan=AnalysisPlan(
            intent=Intent.CHART,
            rationale="Render bar chart for visualization",
            steps=[
                PlanStep(
                    step_number=1,
                    tool=ToolName.CHARTS,
                    description="Render bar chart",
                    parameters={"chart_type": "bar", "x": "Region", "y": "Revenue"},
                )
            ],
        ),
        tool_results=[
            ToolResult(
                tool=ToolName.METRICS,
                step_number=1,
                success=True,
                data=[{"Region": "North", "Revenue": 1000}, {"Region": "South", "Revenue": 2000}],
            )
        ],
        chart_artifacts=[],
    )

    result_state = charts_tool_node(state)
    artifacts = result_state.get("chart_artifacts", [])
    assert len(artifacts) == 1

    fig_dict = artifacts[0]
    assert is_plotly_figure_dict(fig_dict)
    assert fig_dict.get("_chart_id") == "chart_test_run_uuid_s1_0"
    assert fig_dict.get("_step_number") == 1
    assert fig_dict.get("_run_id") == "test_run_uuid"
