"""Acceptance Test Suite Runner for Insight Copilot.

Executes the compact must-pass test pack and multi-turn conversations through the LangGraph engine,
enforcing rate-limit delays, capturing structured logs, and auditing silent correctness.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.graph import build_graph
from agent.state import create_initial_state
from dotenv import load_dotenv
from llm.factory import create_llm
from models.schemas import Message, Role
from utils.data_loader import reset_to_raw_dataset
from utils.logging_config import setup_logging

load_dotenv()

# Configure logging to app.log and stdout
setup_logging(level="INFO")
logger = logging.getLogger("acceptance_runner")

RESULTS_FILE = PROJECT_ROOT / "logs" / "acceptance_test_results.json"
RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_DELAY_SECONDS = 7.0


@dataclass
class TurnResult:
    query: str
    intent: str
    tools: list[str]
    plan_steps: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    synthesizer_response: str
    errors: list[str]
    latencies: dict[str, float]
    citations: list[int]
    passed_checks: list[str]
    failed_checks: list[str]


@dataclass
class TestCaseResult:
    test_id: str
    category: str
    description: str
    turns: list[TurnResult]
    overall_status: str  # PASSED / FAILED
    silent_correctness_notes: list[str]


# ===========================================================================
# Test Cases Definitions (Must-Pass 20 + Core Suites)
# ===========================================================================

TEST_PACK = [
    # 1. Data Cleaning
    {
        "id": "DC-01",
        "category": "Data Cleaning",
        "description": "Detect dirty Region data",
        "type": "single",
        "prompt": "Show me every distinct value in the Region column with its record count. Do not sample the data.",
        "checks": {
            "expected_tools": ["data_clean", "data_profile", "metrics", "data_query"],
            "must_contain_keywords": ["North", "South", "West", "East"],
        },
    },
    {
        "id": "DC-02",
        "category": "Data Cleaning",
        "description": "Normalize Region column",
        "type": "single",
        "prompt": "Clean the Region column by standardizing casing, merging obvious typo variants, and replacing missing values with 'Unassigned'. Show me the exact before -> after mappings and counts.",
        "checks": {
            "expected_tools": ["data_clean"],
            "must_contain_keywords": ["North", "South", "East", "West"],
        },
    },
    {
        "id": "DC-03",
        "category": "Data Cleaning",
        "description": "Clean -> Analyze total revenue by cleaned region",
        "type": "single",
        "prompt": "Clean the Region column and then calculate total revenue by cleaned region.",
        "checks": {
            "expected_tools": ["data_clean", "metrics"],
            "must_contain_keywords": ["Revenue", "Region"],
        },
    },
    {
        "id": "DC-04",
        "category": "Data Cleaning",
        "description": "Clean -> Analyze -> Chart revenue by cleaned region",
        "type": "single",
        "prompt": "Clean the Region column, calculate total revenue by cleaned region, and create a bar chart showing the four canonical regions. Exclude Unassigned.",
        "checks": {
            "expected_tools": ["data_clean", "metrics", "charts"],
        },
    },
    {
        "id": "DC-05",
        "category": "Data Cleaning",
        "description": "Bronze/Silver preservation inspection",
        "type": "conversation",
        "prompts": [
            "Clean the Region column by fixing casing and typo variants.",
            "Show me the distinct raw Region values from the original dataset.",
            "Show me the distinct Region values in the cleaned dataset.",
        ],
    },
    {
        "id": "DC-06",
        "category": "Data Cleaning",
        "description": "Reset active dataset to raw data",
        "type": "conversation",
        "prompts": [
            "Clean the Region column by merging typos.",
            "Reset the active dataset to the raw data and show me the Region distribution again.",
        ],
    },
    {
        "id": "DC-07",
        "category": "Data Cleaning",
        "description": "Product normalization (MOBLIE -> Mobile)",
        "type": "single",
        "prompt": "Normalize the Product column by fixing obvious casing and typo variants. Show me every transformation you applied.",
        "checks": {
            "expected_tools": ["data_clean"],
            "must_contain_keywords": ["Mobile"],
        },
    },
    # 2. Analytical Correctness
    {
        "id": "AC-01",
        "category": "Analytical Correctness",
        "description": "Basic total revenue metric",
        "type": "single",
        "prompt": "What is the total revenue?",
        "checks": {
            "expected_tools": ["metrics"],
        },
    },
    {
        "id": "AC-02",
        "category": "Analytical Correctness",
        "description": "Grouped metric: total revenue by region",
        "type": "single",
        "prompt": "What is total revenue by region?",
        "checks": {
            "expected_tools": ["metrics"],
        },
    },
    {
        "id": "AC-03",
        "category": "Analytical Correctness",
        "description": "Ranking top 5 products by revenue",
        "type": "single",
        "prompt": "Which five products generated the most revenue?",
        "checks": {
            "expected_tools": ["metrics", "profitability"],
        },
    },
    {
        "id": "AC-04",
        "category": "Analytical Correctness",
        "description": "Profit margin ranking",
        "type": "single",
        "prompt": "Calculate the profit margin for every product using Profit divided by Revenue multiplied by 100, and show me the highest five.",
        "checks": {
            "expected_tools": ["profitability", "metrics"],
        },
    },
    {
        "id": "AC-05",
        "category": "Analytical Correctness",
        "description": "Revenue vs Profit leaders comparison",
        "type": "single",
        "prompt": "Which product generates the most revenue, and which generates the most profit? Are they the same?",
        "checks": {
            "expected_tools": ["metrics", "profitability", "compare"],
        },
    },
    {
        "id": "AC-06",
        "category": "Analytical Correctness",
        "description": "Top 3 products revenue contribution percentage",
        "type": "single",
        "prompt": "Show the top three products by revenue and their percentage contribution to total revenue.",
        "checks": {
            "expected_tools": ["contribution", "metrics"],
        },
    },
    {
        "id": "AC-07",
        "category": "Analytical Correctness",
        "description": "Monthly revenue trend for 2024 and highest month",
        "type": "single",
        "prompt": "Show me monthly revenue for 2024 and tell me which month was highest.",
        "checks": {
            "expected_tools": ["trends", "metrics"],
        },
    },
    {
        "id": "AC-08",
        "category": "Analytical Correctness",
        "description": "Numeric scatter plot vs categorical validation",
        "type": "single",
        "prompt": "Create a scatter plot showing Units Sold versus Revenue.",
        "checks": {
            "expected_tools": ["charts"],
        },
    },
    {
        "id": "AC-09",
        "category": "Analytical Correctness",
        "description": "Terminology grounding: COGS and gross margin",
        "type": "single",
        "prompt": "What is the COGS and gross margin for each product?",
        "checks": {},
    },
    # 3. Multi-Turn Context
    {
        "id": "MT-01",
        "category": "Multi-Turn Context",
        "description": "Regional revenue follow-up chain",
        "type": "conversation",
        "prompts": [
            "What is total revenue by region?",
            "Which one is highest?",
            "What about profit?",
            "Show me that as a chart.",
        ],
    },
    {
        "id": "MT-02",
        "category": "Multi-Turn Context",
        "description": "Temporal revenue follow-up chain",
        "type": "conversation",
        "prompts": [
            "Show me monthly revenue for 2024.",
            "Which month was highest?",
            "Was that also the most profitable?",
            "Show me both trends.",
        ],
    },
    {
        "id": "MT-03",
        "category": "Multi-Turn Context",
        "description": "Cleaning and comparative follow-up chain",
        "type": "conversation",
        "prompts": [
            "The Region column looks messy. Can you inspect it?",
            "Clean the obvious problems.",
            "Now show revenue by region.",
            "How different is that from the raw data?",
        ],
    },
    # 4. Unsupported Questions
    {
        "id": "U-01",
        "category": "Unsupported Questions",
        "description": "External market data refusal",
        "type": "single",
        "prompt": "What is Apple's stock price today?",
        "checks": {
            "disallowed_tools": ["metrics", "data_query", "trends"],
        },
    },
    {
        "id": "U-02",
        "category": "Unsupported Questions",
        "description": "Weather refusal",
        "type": "single",
        "prompt": "What's the weather in Pune today?",
        "checks": {
            "disallowed_tools": ["metrics", "data_query"],
        },
    },
    {
        "id": "U-03",
        "category": "Unsupported Questions",
        "description": "Competitor data refusal",
        "type": "single",
        "prompt": "What was our competitor's revenue last year?",
        "checks": {
            "disallowed_tools": ["metrics", "data_query"],
        },
    },
    {
        "id": "U-04",
        "category": "Unsupported Questions",
        "description": "Missing schema field recognition",
        "type": "single",
        "prompt": "Which customer segment generates the most revenue?",
        "checks": {},
    },
    {
        "id": "U-05",
        "category": "Unsupported Questions",
        "description": "Forecasting capability limitation",
        "type": "single",
        "prompt": "Forecast revenue for 2025.",
        "checks": {},
    },
    {
        "id": "U-06",
        "category": "Unsupported Questions",
        "description": "Causal claim with missing evidence",
        "type": "single",
        "prompt": "Did discounts cause lower profit?",
        "checks": {},
    },
]


def run_single_turn(
    compiled_graph: Any,
    query: str,
    history: list[Message] | None = None,
    checks: dict[str, Any] | None = None,
) -> tuple[TurnResult, list[Message]]:
    """Execute a single query turn through the compiled graph."""
    if history is None:
        history = []

    initial_state = create_initial_state(query=query, history=history)

    t_start = time.perf_counter()
    final_state = compiled_graph.invoke(initial_state)
    t_end = time.perf_counter()

    plan = final_state.get("plan")
    intent = final_state.get("intent", "unknown")
    selected_tools = [str(t.value if hasattr(t, "value") else t) for t in final_state.get("selected_tools", [])]

    plan_steps_data = []
    if plan and hasattr(plan, "steps") and plan.steps:
        for s in plan.steps:
            plan_steps_data.append({
                "step": getattr(s, "step", None),
                "tool": getattr(s, "tool", None),
                "parameters": getattr(s, "parameters", {}),
                "depends_on": getattr(s, "depends_on", []),
            })

    tool_results_data = []
    for r in final_state.get("tool_results", []):
        tool_results_data.append({
            "step": getattr(r, "step", None),
            "tool": getattr(r, "tool", None),
            "success": getattr(r, "success", True),
            "error": getattr(r, "error", None),
            "result": getattr(r, "result", None),
        })

    response = final_state.get("final_answer") or ""
    errors = final_state.get("errors", [])

    total_latency_ms = (t_end - t_start) * 1000
    latencies = {"total_ms": round(total_latency_ms, 2)}

    # Extract citations [Step X]
import argparse

def evaluate_turn_checks(
    turn_res_data: dict[str, Any],
    checks: dict[str, Any] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Evaluate deterministic silent-correctness assertions on a single turn."""
    passed_checks: list[str] = []
    failed_checks: list[str] = []
    silent_notes: list[str] = []

    checks = checks or {}
    selected_tools = turn_res_data.get("tools", [])
    response = turn_res_data.get("synthesizer_response", "")
    errors = turn_res_data.get("errors", [])
    plan_steps = turn_res_data.get("plan_steps", [])
    tool_results = turn_res_data.get("tool_results", [])
    citations = turn_res_data.get("citations", [])

    # 1. Expected Tools check
    expected_tools = checks.get("expected_tools")
    if expected_tools:
        if any(t in selected_tools for t in expected_tools):
            passed_checks.append(f"Used expected tool from {expected_tools}")
        else:
            failed_checks.append(
                f"Selected tools {selected_tools} did not match expected {expected_tools}"
            )

    # 2. Exact Tool Sequence check
    exact_sequence = checks.get("exact_sequence")
    if exact_sequence:
        if selected_tools == exact_sequence:
            passed_checks.append(f"Exact tool sequence matched {exact_sequence}")
        else:
            failed_checks.append(
                f"Selected tools {selected_tools} did not match exact sequence {exact_sequence}"
            )

    # 3. Disallowed Tools check
    disallowed_tools = checks.get("disallowed_tools")
    if disallowed_tools:
        if any(t in selected_tools for t in disallowed_tools):
            failed_checks.append(
                f"Used disallowed tool from {disallowed_tools} (selected: {selected_tools})"
            )
        else:
            passed_checks.append(
                f"Properly avoided disallowed tools {disallowed_tools}"
            )

    # 4. Must Contain Keywords check
    must_contain = checks.get("must_contain_keywords")
    if must_contain:
        for kw in must_contain:
            if kw.lower() in response.lower():
                passed_checks.append(f"Contains keyword '{kw}'")
            else:
                failed_checks.append(f"Missing keyword '{kw}'")

    # 5. Citation Audit (Silent-Correctness Gate)
    if tool_results and not errors:
        valid_steps = {r.get("step") for r in tool_results if r.get("step")}
        if citations:
            invalid_citations = set(citations) - valid_steps
            if invalid_citations:
                failed_checks.append(f"Hallucinated citations for non-existent steps: {invalid_citations}")
            else:
                passed_checks.append(f"Citations {citations} strictly refer to valid steps {valid_steps}")
        else:
            silent_notes.append("No explicit [Step X] citations in response text.")

    # 6. Tool Result Integrity
    for res in tool_results:
        if res.get("success") is False:
            failed_checks.append(f"Tool {res.get('tool')} (step {res.get('step')}) reported failure: {res.get('error')}")
        else:
            passed_checks.append(f"Tool {res.get('tool')} (step {res.get('step')}) executed successfully")

    # 7. Response Integrity
    if not errors and response:
        passed_checks.append("Generated successful response without error")
    elif errors:
        failed_checks.append(f"Execution errors: {errors}")

    return passed_checks, failed_checks, silent_notes


def run_single_turn(
    compiled_graph: Any,
    query: str,
    history: list[Message] | None = None,
    checks: dict[str, Any] | None = None,
) -> tuple[TurnResult, list[Message]]:
    """Execute a single query turn through the compiled graph."""
    if history is None:
        history = []

    initial_state = create_initial_state(query=query, history=history)

    t_start = time.perf_counter()
    final_state = compiled_graph.invoke(initial_state)
    t_end = time.perf_counter()

    plan = final_state.get("plan")
    intent = final_state.get("intent", "unknown")
    selected_tools = [str(t.value if hasattr(t, "value") else t) for t in final_state.get("selected_tools", [])]

    plan_steps_data = []
    if plan and hasattr(plan, "steps") and plan.steps:
        for s in plan.steps:
            plan_steps_data.append({
                "step": getattr(s, "step", None),
                "tool": getattr(s, "tool", None),
                "parameters": getattr(s, "parameters", {}),
                "depends_on": getattr(s, "depends_on", []),
            })

    tool_results_data = []
    for r in final_state.get("tool_results", []):
        tool_results_data.append({
            "step": getattr(r, "step", None),
            "tool": getattr(r, "tool", None),
            "success": getattr(r, "success", True),
            "error": getattr(r, "error", None),
            "result": getattr(r, "result", None),
        })

    response = final_state.get("final_answer") or ""
    errors = final_state.get("errors", [])

    total_latency_ms = (t_end - t_start) * 1000
    latencies = {"total_ms": round(total_latency_ms, 2)}

    # Extract citations [Step X]
    citations = [
        int(m) for m in re.findall(r"\[Step\s*(\d+)\]", response, re.IGNORECASE)
    ]

    turn_data = {
        "tools": selected_tools,
        "synthesizer_response": response,
        "errors": errors,
        "plan_steps": plan_steps_data,
        "tool_results": tool_results_data,
        "citations": citations,
    }

    passed_checks, failed_checks, _ = evaluate_turn_checks(turn_data, checks=checks)

    turn_res = TurnResult(
        query=query,
        intent=intent,
        tools=selected_tools,
        plan_steps=plan_steps_data,
        tool_results=tool_results_data,
        synthesizer_response=response,
        errors=errors,
        latencies=latencies,
        citations=citations,
        passed_checks=passed_checks,
        failed_checks=failed_checks,
    )

    updated_messages = list(final_state.get("messages", []))
    return turn_res, updated_messages


def run_acceptance_suite(
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    filter_id: str | None = None,
    output_file: Path | None = None,
    dry_run: bool = False,
) -> list[TestCaseResult]:
    """Run test cases with rate limiting, optional filtering, and dry-run validation."""
    target_results_file = output_file or RESULTS_FILE
    target_results_file.parent.mkdir(parents=True, exist_ok=True)

    test_pack = TEST_PACK
    if filter_id:
        test_pack = [t for t in TEST_PACK if filter_id.lower() in t["id"].lower()]
        logger.info("Filtered test pack to %d cases matching '%s'", len(test_pack), filter_id)

    if dry_run:
        logger.info("Running in dry-run mode (validating test definitions without live execution)...")
        results = []
        for t in test_pack:
            results.append(
                TestCaseResult(
                    test_id=t["id"],
                    category=t["category"],
                    description=t["description"],
                    turns=[],
                    overall_status="PASSED",
                    silent_correctness_notes=["Dry run validated."],
                )
            )
        return results

    logger.info("Initializing LLM and compiling StateGraph...")
    llm = create_llm()
    compiled_graph = build_graph(llm)

    logger.info(
        "Starting Acceptance Test Suite (%d test cases, delay=%.1fs)...",
        len(test_pack),
        delay_seconds,
    )
    all_results: list[TestCaseResult] = []

    for idx, test_spec in enumerate(test_pack, start=1):
        test_id = test_spec["id"]
        category = test_spec["category"]
        desc = test_spec["description"]
        test_type = test_spec.get("type", "single")

        logger.info(
            "[%d/%d] Running %s (%s): %s",
            idx,
            len(test_pack),
            test_id,
            category,
            desc,
        )

        # Ensure clean raw dataset state before each test case
        reset_to_raw_dataset()

        turns_results: list[TurnResult] = []
        silent_notes: list[str] = []

        if test_type == "single":
            prompt = test_spec["prompt"]
            checks = test_spec.get("checks", {})
            try:
                turn_res, _ = run_single_turn(
                    compiled_graph=compiled_graph, query=prompt, checks=checks
                )
                turns_results.append(turn_res)
            except Exception as exc:
                logger.exception("Exception running %s: %s", test_id, exc)
                turns_results.append(
                    TurnResult(
                        query=prompt,
                        intent="error",
                        tools=[],
                        plan_steps=[],
                        tool_results=[],
                        synthesizer_response="",
                        errors=[str(exc)],
                        latencies={},
                        citations=[],
                        passed_checks=[],
                        failed_checks=[f"Fatal exception: {exc}"],
                    )
                )

        elif test_type == "conversation":
            prompts = test_spec.get("prompts", [])
            history: list[Message] = []
            for p_idx, prompt in enumerate(prompts, start=1):
                logger.info("  -> Turn %d: %s", p_idx, prompt)
                try:
                    turn_res, updated_history = run_single_turn(
                        compiled_graph=compiled_graph,
                        query=prompt,
                        history=history,
                    )
                    turns_results.append(turn_res)
                    history = updated_history
                except Exception as exc:
                    logger.exception(
                        "Exception running %s turn %d: %s", test_id, p_idx, exc
                    )
                    turns_results.append(
                        TurnResult(
                            query=prompt,
                            intent="error",
                            tools=[],
                            plan_steps=[],
                            tool_results=[],
                            synthesizer_response="",
                            errors=[str(exc)],
                            latencies={},
                            citations=[],
                            passed_checks=[],
                            failed_checks=[f"Fatal exception: {exc}"],
                        )
                    )

                # Rate-limiting pause between conversational turns
                if p_idx < len(prompts):
                    time.sleep(delay_seconds)

        # Evaluate overall case status
        has_failed_checks = any(len(t.failed_checks) > 0 for t in turns_results)
        has_errors = any(len(t.errors) > 0 for t in turns_results)
        overall_status = (
            "PASSED" if not has_failed_checks and not has_errors else "FAILED"
        )

        test_case_res = TestCaseResult(
            test_id=test_id,
            category=category,
            description=desc,
            turns=turns_results,
            overall_status=overall_status,
            silent_correctness_notes=silent_notes,
        )
        all_results.append(test_case_res)

        # Write intermediate JSON results to disk after each test
        with open(target_results_file, "w", encoding="utf-8") as f:
            json.dump(
                [asdict(r) for r in all_results], f, indent=2, default=str
            )

        # Rate-limiting cooldown pause between test cases
        if idx < len(test_pack):
            time.sleep(delay_seconds)

    # Print summary scorecard
    total = len(all_results)
    passed = sum(1 for r in all_results if r.overall_status == "PASSED")
    failed = total - passed

    print("\n" + "=" * 80)
    print(f"ACCEPTANCE TEST RESULTS: {passed}/{total} PASSED ({failed} FAILED)")
    print("=" * 80)
    for r in all_results:
        status_icon = "PASS" if r.overall_status == "PASSED" else "FAIL"
        print(f"[{status_icon}] {r.test_id:6s} | {r.category:25s} | {r.description}")
        if r.overall_status != "PASSED":
            for t in r.turns:
                for f_chk in t.failed_checks:
                    print(f"       -> Check Failed: {f_chk}")
    print("=" * 80 + "\n")

    return all_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Insight Copilot Acceptance Test Runner")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Delay between LLM calls in seconds")
    parser.add_argument("--filter", type=str, default=None, help="Filter test cases by ID (e.g. DC, AC, MT, U)")
    parser.add_argument("--output", type=Path, default=None, help="Path to save output JSON results")
    parser.add_argument("--dry-run", action="store_true", help="Validate test definitions without live execution")
    args = parser.parse_args()

    run_acceptance_suite(
        delay_seconds=args.delay,
        filter_id=args.filter,
        output_file=args.output,
        dry_run=args.dry_run,
    )
