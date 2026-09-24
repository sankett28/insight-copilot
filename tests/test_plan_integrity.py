"""
tests/test_plan_integrity.py
-----------------------------
Regression tests for the FINAL RELEASE BLOCKER — multi-step plan integrity.

Covers:
  - Bug A/C: planner selected_tools derivation always equals plan.steps length
  - Bug B:   cross-step sentinel parameter resolution (result_resolver)
  - Bug D:   synthesizer does not conflate one metric's ranking with another's

Test names map directly to the required test list in the bug report:
  test_combined_month_revenue_and_top_product
  test_top_salesperson_and_units
  test_top_product_then_profit_dependency
  test_top_region_then_profit_dependency
  test_plan_step_count_matches_execution_steps
  test_no_plan_step_disappears
  test_synthesis_does_not_confuse_profit_ranking_with_revenue_ranking
"""

from __future__ import annotations

import pytest

from agent.planner import build_planner_node
from agent.router import router_node, advance_step, SYNTHESIZER_NODE
from agent.synthesizer import _format_tool_results
from agent.validator import validate_analysis_plan
from models.schemas import (
    AnalysisPlan,
    Intent,
    PlanStep,
    ToolName,
    ToolResult,
)
from utils.result_resolver import resolve_step_parameters


# ---------------------------------------------------------------------------
# Bug A/C — selected_tools always derived from plan.steps
# ---------------------------------------------------------------------------


class _FakeLLMTwoMetricsOneInSelected:
    """Simulates an LLM that returns 2 steps but only 1 entry in selected_tools."""

    def structured_chat(self, messages, schema):
        return AnalysisPlan(
            intent=Intent.COMBINED,
            rationale="Two metrics steps with the same tool.",
            steps=[
                PlanStep(
                    step_number=1,
                    tool=ToolName.METRICS,
                    description="Total revenue in November 2024",
                    parameters={
                        "metric": "Revenue",
                        "aggregation": "sum",
                        "filters": {"Date": "2024-11"},
                    },
                    depends_on=[],
                ),
                PlanStep(
                    step_number=2,
                    tool=ToolName.METRICS,
                    description="Top product by revenue in November 2024",
                    parameters={
                        "metric": "Revenue",
                        "aggregation": "sum",
                        "group_by": "Product",
                        "filters": {"Date": "2024-11"},
                        "limit": 1,
                    },
                    depends_on=[],
                ),
            ],
            # Planner LLM only included one unique tool — the old bug
            selected_tools=[ToolName.METRICS],
        )

    def chat(self, messages, temperature=0.0):
        class _R:
            content = "Mock synthesis"
        return _R()


def _make_state_for_llm(llm) -> dict:
    """Build the minimal AgentState-compatible dict for a planner_node call."""
    from models.schemas import Message, Role
    return {
        "query": "How much revenue was generated in November 2024, and which product generated the most revenue?",
        "messages": [
            Message(role=Role.USER, content="How much revenue in Nov 2024?")
        ],
        "tool_results": [],
        "chart_artifacts": [],
        "errors": [],
        "run_id": "test-run",
        "telemetry": {},
        "current_step": 0,
    }


def test_plan_step_count_matches_execution_steps():
    """selected_tools must have the same length as plan.steps — always."""
    llm = _FakeLLMTwoMetricsOneInSelected()
    planner_node = build_planner_node(llm)
    state = _make_state_for_llm(llm)
    result = planner_node(state)

    plan: AnalysisPlan = result["plan"]
    selected_tools: list = result["selected_tools"]

    assert len(plan.steps) == 2, f"Expected 2 plan steps, got {len(plan.steps)}"
    assert len(selected_tools) == 2, (
        f"selected_tools length {len(selected_tools)} != plan.steps length {len(plan.steps)}. "
        f"The planner must always derive selected_tools from plan.steps."
    )
    assert selected_tools[0] == ToolName.METRICS
    assert selected_tools[1] == ToolName.METRICS


def test_no_plan_step_disappears():
    """Router must execute exactly as many steps as plan.steps contains."""
    # Craft a plan where both steps use the same tool (the old bug scenario)
    plan = AnalysisPlan(
        intent=Intent.COMBINED,
        rationale="Two metrics steps",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Total revenue",
                parameters={"metric": "Revenue", "aggregation": "sum"},
                depends_on=[],
            ),
            PlanStep(
                step_number=2,
                tool=ToolName.METRICS,
                description="Revenue by product",
                parameters={"metric": "Revenue", "aggregation": "sum", "group_by": "Product"},
                depends_on=[],
            ),
        ],
        selected_tools=[ToolName.METRICS, ToolName.METRICS],  # correctly derived
    )

    # Simulate the two router passes as the graph would see them
    state_after_step0 = {
        "plan": plan,
        "selected_tools": [ToolName.METRICS, ToolName.METRICS],
        "current_step": 0,
        "tool_results": [],
        "errors": [],
    }
    route_0 = router_node(state_after_step0)
    assert route_0 == "metrics", f"Step 0 should route to metrics, got: {route_0}"

    # Advance and route step 1
    advance_result = advance_step(state_after_step0)
    state_after_step1 = {
        **state_after_step0,
        "current_step": advance_result["current_step"],
        "tool_results": [
            ToolResult(
                tool=ToolName.METRICS,
                step_number=1,
                success=True,
                data=[{"sum_revenue": 100000}],
            )
        ],
    }
    route_1 = router_node(state_after_step1)
    assert route_1 == "metrics", f"Step 1 should route to metrics, got: {route_1}"

    # Advance and confirm routing to synthesizer
    advance_result2 = advance_step(state_after_step1)
    state_final = {
        **state_after_step1,
        "current_step": advance_result2["current_step"],
    }
    route_final = router_node(state_final)
    assert route_final == SYNTHESIZER_NODE, (
        f"After both steps, router should route to synthesizer, got: {route_final}"
    )


def test_combined_month_revenue_and_top_product():
    """Bug A: Two-step plan with same tool (metrics) must produce len(selected_tools)==2."""
    llm = _FakeLLMTwoMetricsOneInSelected()
    planner_node = build_planner_node(llm)
    result = planner_node(_make_state_for_llm(llm))
    assert len(result["selected_tools"]) == 2
    assert len(result["plan"].steps) == 2


def test_top_salesperson_and_units():
    """Bug A: Same as above for salesperson + units query pattern."""

    class _FakeLLM:
        def structured_chat(self, messages, schema):
            return AnalysisPlan(
                intent=Intent.COMBINED,
                rationale="Top salesperson by revenue and their unit count.",
                steps=[
                    PlanStep(
                        step_number=1,
                        tool=ToolName.METRICS,
                        description="Revenue by salesperson",
                        parameters={
                            "metric": "Revenue",
                            "aggregation": "sum",
                            "group_by": "Salesperson",
                            "limit": 1,
                        },
                    ),
                    PlanStep(
                        step_number=2,
                        tool=ToolName.METRICS,
                        description="Units sold by top salesperson",
                        parameters={
                            "metric": "Units_Sold",
                            "aggregation": "sum",
                            "filters": {"Salesperson": "__step_1_top_Salesperson"},
                        },
                        depends_on=[1],
                    ),
                ],
                selected_tools=[ToolName.METRICS],  # bug: only 1 entry
            )

        def chat(self, messages, temperature=0.0):
            class _R:
                content = "mock"
            return _R()

    llm = _FakeLLM()
    result = build_planner_node(llm)(_make_state_for_llm(llm))
    assert len(result["selected_tools"]) == 2
    assert len(result["plan"].steps) == 2


# ---------------------------------------------------------------------------
# Bug B — cross-step result propagation (result_resolver)
# ---------------------------------------------------------------------------


def test_top_region_then_profit_dependency():
    """Bug B: Sentinel __step_1_top_Region resolves to West from step 1 result."""
    step1_result = ToolResult(
        tool=ToolName.METRICS,
        step_number=1,
        success=True,
        data=[
            {"Region": "West", "sum_revenue": 500000},
            {"Region": "North", "sum_revenue": 400000},
        ],
    )

    raw_params = {
        "metric": "Profit",
        "aggregation": "sum",
        "filters": {"Region": "__step_1_top_Region"},
    }

    resolved = resolve_step_parameters(raw_params, [step1_result])

    assert resolved["filters"]["Region"] == "West", (
        f"Expected 'West' from step 1 top row, got: {resolved['filters']['Region']}"
    )
    # Sentinel must NOT remain as the raw string
    assert "__step_" not in str(resolved["filters"]["Region"]), (
        "Sentinel string was not resolved — step 2 would have queried the wrong region."
    )


def test_top_product_then_profit_dependency():
    """Bug B: Sentinel __step_1_top_Product resolves correctly from step 1."""
    step1_result = ToolResult(
        tool=ToolName.METRICS,
        step_number=1,
        success=True,
        data=[
            {"Product": "Widget Pro", "sum_revenue": 300000},
            {"Product": "Widget Lite", "sum_revenue": 200000},
        ],
    )

    raw_params = {
        "metric": "Profit",
        "aggregation": "sum",
        "filters": {"Product": "__step_1_top_Product"},
    }

    resolved = resolve_step_parameters(raw_params, [step1_result])
    assert resolved["filters"]["Product"] == "Widget Pro"


def test_sentinel_not_resolved_when_step_not_complete():
    """Bug B: If step N is not done yet, sentinel must remain (not substituted with None)."""
    raw_params = {"filters": {"Region": "__step_1_top_Region"}}
    resolved = resolve_step_parameters(raw_params, [])  # no tool results
    # Sentinel must be left as-is, not replaced with None or empty string
    assert resolved["filters"]["Region"] == "__step_1_top_Region"


def test_sentinel_not_resolved_when_step_failed():
    """Bug B: If step N failed, sentinel must remain."""
    step1_failed = ToolResult(
        tool=ToolName.METRICS,
        step_number=1,
        success=False,
        data=None,
        error="DuckDB error",
    )
    raw_params = {"filters": {"Region": "__step_1_top_Region"}}
    resolved = resolve_step_parameters(raw_params, [step1_failed])
    assert resolved["filters"]["Region"] == "__step_1_top_Region"


def test_sentinel_nested_in_filters_dict():
    """Bug B: Resolver must work when sentinel is nested inside a dict value."""
    step1_result = ToolResult(
        tool=ToolName.METRICS,
        step_number=1,
        success=True,
        data=[{"Salesperson": "Alice", "sum_revenue": 900000}],
    )
    raw_params = {"filters": {"Salesperson": "__step_1_top_Salesperson"}}
    resolved = resolve_step_parameters(raw_params, [step1_result])
    assert resolved["filters"]["Salesperson"] == "Alice"


def test_non_sentinel_params_untouched():
    """Bug B: Regular parameter values must pass through the resolver unchanged."""
    raw_params = {
        "metric": "Revenue",
        "aggregation": "sum",
        "group_by": "Region",
        "filters": {"Region": "North"},
        "limit": 10,
    }
    resolved = resolve_step_parameters(raw_params, [])
    assert resolved == raw_params


# ---------------------------------------------------------------------------
# Bug D — synthesizer does not conflate profit ranking with revenue ranking
# ---------------------------------------------------------------------------


def test_synthesis_does_not_confuse_profit_ranking_with_revenue_ranking():
    """Bug D: When data is sorted by sum_profit, the ranking note must say 'profit',
    NOT 'revenue'.  The RANKING NOTE is embedded in the formatted result text.
    """
    # Simulate a metrics tool result sorted by profit DESC
    profit_result = ToolResult(
        tool=ToolName.METRICS,
        step_number=1,
        success=True,
        data=[
            {"Region": "West", "sum_profit": 150000},
            {"Region": "North", "sum_profit": 120000},
            {"Region": "South", "sum_profit": 80000},
        ],
        source_view="dataset",
        row_count=3,
        execution_time_ms=45.0,
    )

    formatted = _format_tool_results([profit_result])

    # The RANKING NOTE must identify the correct sort metric
    assert "sum_profit" in formatted, (
        "RANKING NOTE must name 'sum_profit' as the sort metric, not be absent."
    )
    assert "RANKING NOTE" in formatted, (
        "_format_tool_results must include a RANKING NOTE for sorted results."
    )

    # Critically: the note must NOT claim 'sum_revenue' is the sort key
    assert "sorted DESC by 'sum_profit'" in formatted, (
        "RANKING NOTE must explicitly state sorted by 'sum_profit'."
    )


def test_synthesis_ranking_note_absent_for_non_aggregate_data():
    """Bug D: No RANKING NOTE when result has no aggregate (agg prefix) columns."""
    raw_result = ToolResult(
        tool=ToolName.DATA_QUERY,
        step_number=1,
        success=True,
        data=[
            {"Region": "West", "Revenue": 5000},
        ],
        source_view="dataset",
        row_count=1,
        execution_time_ms=10.0,
    )
    formatted = _format_tool_results([raw_result])
    # No aggregate columns → no RANKING NOTE should be injected
    assert "RANKING NOTE" not in formatted


def test_synthesis_ranking_note_for_revenue_result():
    """Bug D: When sorted by sum_revenue, the note must say 'sum_revenue', not 'sum_profit'."""
    revenue_result = ToolResult(
        tool=ToolName.METRICS,
        step_number=1,
        success=True,
        data=[
            {"Salesperson": "Alice", "sum_revenue": 900000},
            {"Salesperson": "Bob", "sum_revenue": 800000},
        ],
        source_view="dataset",
        row_count=2,
        execution_time_ms=30.0,
    )
    formatted = _format_tool_results([revenue_result])
    assert "sum_revenue" in formatted
    assert "sorted DESC by 'sum_revenue'" in formatted


# ---------------------------------------------------------------------------
# Validator sentinel awareness
# ---------------------------------------------------------------------------


def test_validator_allows_sentinel_step_without_error():
    """Validator must NOT reject steps with __step_N_top_FIELD sentinel parameters."""
    plan = AnalysisPlan(
        intent=Intent.COMBINED,
        rationale="Step 2 depends on step 1 result.",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Revenue by region",
                parameters={
                    "metric": "Revenue",
                    "aggregation": "sum",
                    "group_by": "Region",
                    "limit": 1,
                },
                depends_on=[],
            ),
            PlanStep(
                step_number=2,
                tool=ToolName.METRICS,
                description="Profit for top region",
                parameters={
                    "metric": "Profit",
                    "aggregation": "sum",
                    # Sentinel will be resolved at execution time
                    "filters": {"Region": "__step_1_top_Region"},
                },
                depends_on=[1],
            ),
        ],
        selected_tools=[ToolName.METRICS, ToolName.METRICS],
    )

    result = validate_analysis_plan(plan)
    # Step 2 has a sentinel — validator must NOT flag it as an error
    assert result.is_valid, (
        f"Validator should accept sentinel parameters without error. "
        f"Errors: {result.errors}"
    )
    # A warning is acceptable
    assert any("sentinel" in w.lower() for w in result.warnings), (
        "Validator should emit a warning for deferred sentinel validation."
    )
