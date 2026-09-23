"""Unit tests for Acceptance Test Suite Runner and deterministic silent correctness gates."""

import pytest
from pathlib import Path
from scripts.acceptance_test_runner import (
    TEST_PACK,
    evaluate_turn_checks,
    run_acceptance_suite,
)


def test_acceptance_test_pack_structure():
    """Verify acceptance test pack contains all required test cases and valid schema."""
    assert len(TEST_PACK) >= 20, f"Expected at least 20 acceptance tests, found {len(TEST_PACK)}"
    
    seen_ids = set()
    for test in TEST_PACK:
        test_id = test.get("id")
        assert test_id, "Test case missing 'id'"
        assert test_id not in seen_ids, f"Duplicate test ID: {test_id}"
        seen_ids.add(test_id)
        
        assert "category" in test, f"Test {test_id} missing category"
        assert "description" in test, f"Test {test_id} missing description"
        assert "type" in test, f"Test {test_id} missing type"
        
        if test["type"] == "single":
            assert "prompt" in test, f"Single-turn test {test_id} missing prompt"
        elif test["type"] == "conversation":
            assert "prompts" in test and len(test["prompts"]) >= 2, f"Multi-turn test {test_id} missing prompts list"


def test_evaluate_turn_checks_expected_and_disallowed_tools():
    """Test deterministic evaluation of expected and disallowed tools."""
    turn_data = {
        "tools": ["metrics", "charts"],
        "synthesizer_response": "Total revenue is $1,000,000 [Step 1].",
        "errors": [],
        "plan_steps": [{"step": 1, "tool": "metrics"}, {"step": 2, "tool": "charts"}],
        "tool_results": [{"step": 1, "tool": "metrics", "success": True}],
        "citations": [1],
    }

    # Pass case
    passed, failed, _ = evaluate_turn_checks(
        turn_data,
        checks={"expected_tools": ["metrics"], "disallowed_tools": ["data_clean"]},
    )
    assert len(failed) == 0
    assert any("Used expected tool" in p for p in passed)
    assert any("Properly avoided disallowed tools" in p for p in passed)

    # Fail case - expected tool missing
    passed, failed, _ = evaluate_turn_checks(
        turn_data,
        checks={"expected_tools": ["trends"]},
    )
    assert any("did not match expected" in f for f in failed)

    # Fail case - disallowed tool present
    passed, failed, _ = evaluate_turn_checks(
        turn_data,
        checks={"disallowed_tools": ["metrics"]},
    )
    assert any("Used disallowed tool" in f for f in failed)


def test_evaluate_turn_checks_citation_audit():
    """Test silent correctness citation gate (detecting hallucinated citation steps)."""
    turn_data = {
        "tools": ["metrics"],
        "synthesizer_response": "Total revenue is $1,000,000 [Step 1] and [Step 99].",
        "errors": [],
        "plan_steps": [{"step": 1, "tool": "metrics"}],
        "tool_results": [{"step": 1, "tool": "metrics", "success": True}],
        "citations": [1, 99],
    }

    passed, failed, _ = evaluate_turn_checks(turn_data, checks={})
    assert any("Hallucinated citations for non-existent steps" in f for f in failed)


def test_acceptance_suite_dry_run():
    """Verify that acceptance suite dry-run mode validates all test cases without live API calls."""
    results = run_acceptance_suite(dry_run=True)
    assert len(results) == len(TEST_PACK)
    assert all(r.overall_status == "PASSED" for r in results)
