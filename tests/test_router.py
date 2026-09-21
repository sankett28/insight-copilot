"""
tests/test_router.py
---------------------
Unit tests for agent/router.py.
"""

from agent.router import ERROR_NODE, SYNTHESIZER_NODE, advance_step, router_node
from agent.state import AgentState
from models.schemas import AnalysisPlan, Intent, PlanStep, ToolName, ToolResult


def test_router_single_step():
    """Route step 0 to the first tool node."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Category revenue comparison",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Category revenue",
            )
        ],
        selected_tools=[ToolName.METRICS],
    )
    state: AgentState = {
        "plan": plan,
        "selected_tools": [ToolName.METRICS],
        "current_step": 0,
        "errors": [],
    }
    assert router_node(state) == "metrics"


def test_router_multi_step_dependency_success():
    """Route to step 2 after step 1 succeeds."""
    plan = AnalysisPlan(
        intent=Intent.COMBINED,
        rationale="Trend + Chart",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.TRENDS,
                description="Monthly trend",
                depends_on=[],
            ),
            PlanStep(
                step_number=2,
                tool=ToolName.CHARTS,
                description="Line chart",
                depends_on=[1],
            ),
        ],
        selected_tools=[ToolName.TRENDS, ToolName.CHARTS],
    )

    step1_result = ToolResult(
        tool=ToolName.TRENDS,
        step_number=1,
        success=True,
        data=[{"period": "2024-01-01", "total_revenue": 100}],
    )

    state: AgentState = {
        "plan": plan,
        "selected_tools": [ToolName.TRENDS, ToolName.CHARTS],
        "current_step": 1,
        "tool_results": [step1_result],
        "errors": [],
    }

    assert router_node(state) == "charts"


def test_router_dependency_failed_routes_to_error():
    """Route to error_handler if dependent step 1 failed."""
    plan = AnalysisPlan(
        intent=Intent.COMBINED,
        rationale="Trend + Chart",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.TRENDS,
                description="Monthly trend",
                depends_on=[],
            ),
            PlanStep(
                step_number=2,
                tool=ToolName.CHARTS,
                description="Line chart",
                depends_on=[1],
            ),
        ],
        selected_tools=[ToolName.TRENDS, ToolName.CHARTS],
    )

    step1_failed = ToolResult(
        tool=ToolName.TRENDS,
        step_number=1,
        success=False,
        error="Trend calculation failed",
    )

    state: AgentState = {
        "plan": plan,
        "selected_tools": [ToolName.TRENDS, ToolName.CHARTS],
        "current_step": 1,
        "tool_results": [step1_failed],
        "errors": [],
    }

    assert router_node(state) == ERROR_NODE


def test_router_all_steps_complete_routes_to_synthesizer():
    """Route to synthesizer when current_step equals total steps."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Metrics",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Metrics",
            )
        ],
        selected_tools=[ToolName.METRICS],
    )
    state: AgentState = {
        "plan": plan,
        "selected_tools": [ToolName.METRICS],
        "current_step": 1,
        "errors": [],
    }
    assert router_node(state) == SYNTHESIZER_NODE


def test_advance_step():
    """Verify advance_step node increments current_step."""
    state: AgentState = {"current_step": 0}
    res = advance_step(state)
    assert res == {"current_step": 1}
