"""
tests/evaluation/test_evaluation_suite.py
-----------------------------------------
Automated unit and regression tests for the evaluation harness and benchmark dataset.
"""

from pathlib import Path
import pytest

from agent.validator import validate_analysis_plan
from models.schemas import ToolName
from tests.evaluation.run_eval import (
    build_deterministic_plan_from_case,
    evaluate_single_case,
    load_dataset,
    run_benchmark_evaluation,
)
from utils.capability_registry import REGISTRY

DATASET_PATH = Path(__file__).resolve().parent / "eval_dataset.json"


@pytest.fixture(scope="module")
def eval_dataset():
    """Load benchmark evaluation dataset."""
    return load_dataset(DATASET_PATH)


def test_benchmark_dataset_structure_and_coverage(eval_dataset):
    """Verify evaluation dataset contains ≥30 cases and covers all analytical categories."""
    assert len(eval_dataset) >= 30, f"Expected ≥30 test cases, got {len(eval_dataset)}"

    categories = {case["category"] for case in eval_dataset}
    expected_categories = {
        "single_tool_metrics",
        "single_tool_trends",
        "single_tool_profitability",
        "single_tool_compare",
        "single_tool_contribution",
        "single_tool_variance",
        "single_tool_data_query",
        "single_tool_data_profile",
        "multi_tool_visualization",
        "advanced_statistical",
        "data_cleaning",
        "meta_system",
        "adversarial_out_of_domain",
    }
    assert expected_categories.issubset(categories), f"Missing categories: {expected_categories - categories}"

    # Verify each case has valid ID and query
    for case in eval_dataset:
        assert "id" in case and case["id"].startswith("eval_")
        assert "query" in case and len(case["query"]) > 5
        assert "expected_intent" in case
        assert "expected_tools" in case
        for tool in case["expected_tools"]:
            assert tool in [t.value for t in ToolName], f"Invalid tool: {tool}"


def test_benchmark_parameter_schemas_valid(eval_dataset):
    """Verify all benchmark parameter sets strictly pass capability Pydantic input schemas."""
    for case in eval_dataset:
        tools = case.get("expected_tools", [])
        params_list = case.get("expected_params", [])
        assert len(tools) == len(params_list), f"Case {case['id']} mismatch between tools and params count"

        for tool_name, params in zip(tools, params_list):
            cap = REGISTRY[tool_name]
            # Should validate without raising ValidationError
            validated_model = cap.input_schema.model_validate(params)
            assert validated_model is not None


def test_benchmark_plans_pass_pre_execution_validation(eval_dataset):
    """Verify all benchmark test case plans pass validate_analysis_plan."""
    for case in eval_dataset:
        plan = build_deterministic_plan_from_case(case)
        validation_res = validate_analysis_plan(plan)
        assert validation_res.is_valid, f"Case {case['id']} failed validation: {validation_res.errors}"


def test_benchmark_deterministic_execution_success(eval_dataset):
    """Verify that all executable in-domain test cases complete with 100% execution success on DuckDB."""
    for case in eval_dataset:
        if not case.get("is_in_domain", True) or not case.get("expected_tools", []):
            continue

        result = evaluate_single_case(case, live_mode=False)
        assert result.execution_success is True, f"Case {case['id']} failed execution: {result.error_message}"
        assert result.parameters_valid is True


def test_benchmark_runner_scorecard_metrics(tmp_path):
    """Verify complete evaluation runner produces a 100% parameter validity and execution score."""
    output_report = tmp_path / "eval_report.md"
    scorecard = run_benchmark_evaluation(DATASET_PATH, live_mode=False, output_path=output_report)

    assert scorecard.total_queries >= 30
    assert scorecard.intent_accuracy_pct == 100.0
    assert scorecard.tool_match_pct == 100.0
    assert scorecard.parameter_validity_pct == 100.0
    assert scorecard.execution_success_pct == 100.0

    # Ensure report file was written and contains key scorecard sections
    assert output_report.exists()
    content = output_report.read_text(encoding="utf-8")
    assert "# Insight Copilot Automated Evaluation Report" in content
    assert "Aggregate Benchmark Metrics" in content
