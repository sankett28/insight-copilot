"""
tests/test_validator.py
-----------------------
Unit tests for the centralized pre-execution plan validator (agent/validator.py).
"""

import pytest

from agent.validator import validate_analysis_plan, PlanValidationResult
from models.schemas import AnalysisPlan, Intent, PlanStep, ToolName


def test_validate_none_plan():
    """Verify validate_analysis_plan returns invalid when plan is None."""
    res = validate_analysis_plan(None)
    assert res.is_valid is False
    assert len(res.errors) == 1
    assert "Analysis plan is None" in res.errors[0]


def test_validate_conversational_empty_plan():
    """Verify empty plan with no tools and unknown intent is valid."""
    plan = AnalysisPlan(
        intent=Intent.UNKNOWN,
        rationale="Conversational greeting",
        steps=[],
        selected_tools=[],
    )
    res = validate_analysis_plan(plan)
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_validate_valid_single_step_plan():
    """Verify a properly structured single-step metrics plan passes validation."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Compute total revenue by region",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Sum revenue grouped by region",
                parameters={"metric": "Revenue", "aggregation": "sum", "group_by": "Region"},
                depends_on=[],
            )
        ],
        selected_tools=[ToolName.METRICS],
    )
    res = validate_analysis_plan(plan)
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_validate_valid_multi_step_plan_with_dependency():
    """Verify a valid 2-step plan (trends -> charts) passes validation."""
    plan = AnalysisPlan(
        intent=Intent.COMBINED,
        rationale="Monthly profit trend with a bar chart",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.TRENDS,
                description="Monthly profit aggregation",
                parameters={"metric": "Profit", "granularity": "month"},
                depends_on=[],
            ),
            PlanStep(
                step_number=2,
                tool=ToolName.CHARTS,
                description="Render bar chart of monthly profit",
                parameters={"chart_type": "bar", "x": "period", "y": "total_profit"},
                depends_on=[1],
            ),
        ],
        selected_tools=[ToolName.TRENDS, ToolName.CHARTS],
    )
    res = validate_analysis_plan(plan)
    assert res.is_valid is True
    assert len(res.errors) == 0


def test_validate_non_contiguous_step_numbers():
    """Verify error when step numbers have gaps (e.g. 1, 3)."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Non-contiguous steps",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.DATA_PROFILE,
                description="Profile dataset",
                parameters={},
                depends_on=[],
            ),
            PlanStep(
                step_number=3,
                tool=ToolName.METRICS,
                description="Compute revenue",
                parameters={"metric": "Revenue"},
                depends_on=[],
            ),
        ],
        selected_tools=[ToolName.DATA_PROFILE, ToolName.METRICS],
    )
    res = validate_analysis_plan(plan)
    assert res.is_valid is False
    assert any("strictly sequential from 1 to 2" in err for err in res.errors)


def test_validate_duplicate_step_numbers():
    """Verify error when multiple steps share the same step_number."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Duplicate step numbers",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.DATA_PROFILE,
                description="Profile dataset",
                parameters={},
                depends_on=[],
            ),
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Compute revenue",
                parameters={"metric": "Revenue"},
                depends_on=[],
            ),
        ],
        selected_tools=[ToolName.DATA_PROFILE, ToolName.METRICS],
    )
    res = validate_analysis_plan(plan)
    assert res.is_valid is False
    assert any("Duplicate step_number 1" in err for err in res.errors)


def test_validate_out_of_order_step_numbers():
    """Verify error when steps are [2, 1]."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Out of order steps",
        steps=[
            PlanStep(
                step_number=2,
                tool=ToolName.DATA_PROFILE,
                description="Profile dataset",
                parameters={},
                depends_on=[],
            ),
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Compute revenue",
                parameters={"metric": "Revenue"},
                depends_on=[],
            ),
        ],
        selected_tools=[ToolName.DATA_PROFILE, ToolName.METRICS],
    )
    res = validate_analysis_plan(plan)
    assert res.is_valid is False
    assert any("strictly sequential from 1 to 2" in err for err in res.errors)


def test_validate_forward_dependency():
    """Verify error when step 1 declares dependency on step 2."""
    plan = AnalysisPlan(
        intent=Intent.COMBINED,
        rationale="Forward dependency",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Compute revenue",
                parameters={"metric": "Revenue"},
                depends_on=[2],
            ),
            PlanStep(
                step_number=2,
                tool=ToolName.CHARTS,
                description="Render chart",
                parameters={"chart_type": "bar", "x": "Region", "y": "Revenue"},
                depends_on=[],
            ),
        ],
        selected_tools=[ToolName.METRICS, ToolName.CHARTS],
    )
    res = validate_analysis_plan(plan)
    assert res.is_valid is False
    assert any("forward dependency" in err for err in res.errors)


def test_validate_self_dependency():
    """Verify error when step 1 declares dependency on itself."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Self dependency",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Compute revenue",
                parameters={"metric": "Revenue"},
                depends_on=[1],
            )
        ],
        selected_tools=[ToolName.METRICS],
    )
    res = validate_analysis_plan(plan)
    assert res.is_valid is False
    assert any("cannot depend on itself" in err for err in res.errors)


def test_validate_non_existent_dependency_id():
    """Verify error when step depends on non-existent step 99."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Non-existent dep",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Compute revenue",
                parameters={"metric": "Revenue"},
                depends_on=[99],
            )
        ],
        selected_tools=[ToolName.METRICS],
    )
    res = validate_analysis_plan(plan)
    assert res.is_valid is False
    assert any("forward dependency" in err or "non-existent" in err for err in res.errors)


def test_validate_invalid_parameter_schema():
    """Verify error when required parameter is missing or invalid."""
    plan = AnalysisPlan(
        intent=Intent.COMBINED,
        rationale="Missing compare required fields",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.COMPARE,
                description="Invalid compare request",
                parameters={"metric": "Revenue"},  # missing dimension, value_a, value_b
                depends_on=[],
            )
        ],
        selected_tools=[ToolName.COMPARE],
    )
    res = validate_analysis_plan(plan)
    assert res.is_valid is False
    assert any("parameter validation failed" in err for err in res.errors)


def test_validate_invalid_column_name():
    """Verify error when parameter specifies non-existent dataset column."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Invalid metric column",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Aggregate invalid column",
                parameters={"metric": "NonExistentColumn"},
                depends_on=[],
            )
        ],
        selected_tools=[ToolName.METRICS],
    )
    res = validate_analysis_plan(plan)
    assert res.is_valid is False
    assert any("parameter validation failed" in err for err in res.errors)


def test_validate_empty_steps_with_selected_tools():
    """Verify error when plan has selected_tools but 0 steps."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Mismatched tools and steps",
        steps=[],
        selected_tools=[ToolName.METRICS],
    )
    res = validate_analysis_plan(plan)
    assert res.is_valid is False
    assert any("contains 0 execution steps" in err for err in res.errors)
