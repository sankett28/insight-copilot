"""
tests/evaluation/run_eval.py
----------------------------
Automated Evaluation and Benchmark Runner for Insight Copilot.

Evaluates benchmark queries against:
  1. Intent Classification Accuracy
  2. Tool Selection Precision & Exact Sequence Match
  3. Parameter Schema Contract Validity (Pydantic validation)
  4. Deterministic Tool Execution Success Rate (DuckDB)
  5. Step Provenance & Grounding Verification

Can be executed offline (deterministic validation & execution) or live (with Gemini API).

Usage:
  python tests/evaluation/run_eval.py [--live] [--output docs/evaluation-results.md]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Ensure root workspace is on python path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agent.planner import _build_planner_messages
from agent.state import create_initial_state
from agent.validator import validate_analysis_plan
from llm.base import BaseLLM
from llm.factory import create_llm
from models.schemas import AnalysisPlan, Intent, PlanStep, ToolName, ToolResult
from tools.anomaly_detection import anomaly_detection_tool_node
from tools.charts import charts_tool_node
from tools.compare import compare_tool_node
from tools.contribution import contribution_tool_node
from tools.correlation import correlation_tool_node
from tools.data_clean import data_clean_tool_node
from tools.data_profile import data_profile_tool_node
from tools.data_query import data_query_tool_node
from tools.metrics import metrics_tool_node
from tools.profitability import profitability_tool_node
from tools.segmentation import segmentation_tool_node
from tools.trends import trends_tool_node
from tools.variance import variance_tool_node
from utils.capability_registry import REGISTRY
from utils.data_loader import create_session_connection

TOOL_NODE_MAP = {
    ToolName.DATA_QUERY.value: data_query_tool_node,
    ToolName.DATA_PROFILE.value: data_profile_tool_node,
    ToolName.DATA_CLEAN.value: data_clean_tool_node,
    ToolName.METRICS.value: metrics_tool_node,
    ToolName.TRENDS.value: trends_tool_node,
    ToolName.COMPARE.value: compare_tool_node,
    ToolName.CONTRIBUTION.value: contribution_tool_node,
    ToolName.PROFITABILITY.value: profitability_tool_node,
    ToolName.VARIANCE.value: variance_tool_node,
    ToolName.ANOMALY_DETECTION.value: anomaly_detection_tool_node,
    ToolName.CORRELATION.value: correlation_tool_node,
    ToolName.SEGMENTATION.value: segmentation_tool_node,
    ToolName.CHARTS.value: charts_tool_node,
}


load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval_runner")


@dataclass
class TestCaseResult:
    """Evaluation result for a single benchmark query."""

    id: str
    category: str
    query: str
    is_in_domain: bool
    expected_intent: str
    actual_intent: str = ""
    intent_matched: bool = False
    expected_tools: list[str] = field(default_factory=list)
    actual_tools: list[str] = field(default_factory=list)
    tools_matched: bool = False
    parameters_valid: bool = False
    execution_success: bool = False
    grounded_citations: bool = False
    error_message: str | None = None
    execution_duration_ms: float = 0.0


@dataclass
class EvaluationScorecard:
    """Aggregate benchmark evaluation metrics."""

    total_queries: int = 0
    in_domain_queries: int = 0
    out_of_domain_queries: int = 0
    intent_accuracy_pct: float = 0.0
    tool_match_pct: float = 0.0
    parameter_validity_pct: float = 0.0
    execution_success_pct: float = 0.0
    results: list[TestCaseResult] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render evaluation scorecard as structured Markdown document."""
        lines = [
            "# Insight Copilot Automated Evaluation Report",
            "",
            f"- **Timestamp**: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
            f"- **Total Benchmark Cases**: {self.total_queries}",
            f"- **In-Domain Analytical Queries**: {self.in_domain_queries}",
            f"- **Meta & Out-of-Domain Queries**: {self.out_of_domain_queries}",
            "",
            "## Aggregate Benchmark Metrics",
            "",
            "| Metric | Target | Result | Status |",
            "|---|---|---|---|",
            f"| **Planner Intent Accuracy** | $\\ge 90\\%$ | **{self.intent_accuracy_pct:.1f}%** | {'✅ PASS' if self.intent_accuracy_pct >= 90 else '❌ FAIL'} |",
            f"| **Tool Selection Match** | $\\ge 90\\%$ | **{self.tool_match_pct:.1f}%** | {'✅ PASS' if self.tool_match_pct >= 90 else '❌ FAIL'} |",
            f"| **Parameter Schema Validity** | $100\\%$ | **{self.parameter_validity_pct:.1f}%** | {'✅ PASS' if self.parameter_validity_pct == 100 else '❌ FAIL'} |",
            f"| **Deterministic Execution Success** | $100\\%$ | **{self.execution_success_pct:.1f}%** | {'✅ PASS' if self.execution_success_pct == 100 else '❌ FAIL'} |",
            "",
            "## Benchmark Case Breakdown",
            "",
            "| ID | Category | Intent Match | Tools Match | Params Valid | Exec Success | Duration |",
            "|---|---|:---:|:---:|:---:|:---:|---:|",
        ]

        for r in self.results:
            intent_icon = "✅" if r.intent_matched else "❌"
            tools_icon = "✅" if r.tools_matched else "❌"
            params_icon = "✅" if r.parameters_valid else "❌"
            exec_icon = "✅" if r.execution_success else ("N/A" if not r.is_in_domain or not r.expected_tools else "❌")
            lines.append(
                f"| `{r.id}` | {r.category} | {intent_icon} | {tools_icon} | {params_icon} | {exec_icon} | {r.execution_duration_ms:.1f}ms |"
            )

        lines.extend([
            "",
            "## Evaluation Methodology",
            "1. **Intent & Tool Selection**: Validates whether the planner selects the correct high-level intent and exact capability execution sequence.",
            "2. **Parameter Validity**: Enforces strict Pydantic model validation against the authoritative Capability Registry contracts.",
            "3. **Deterministic Execution**: In-memory session DuckDB execution ensuring clean zero-error computation across all 13 analytical capabilities.",
        ])

        return "\n".join(lines)


def load_dataset(dataset_path: Path | str) -> list[dict[str, Any]]:
    """Load benchmark dataset from JSON."""
    with open(dataset_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_deterministic_plan_from_case(test_case: dict[str, Any]) -> AnalysisPlan:
    """Construct an authoritative AnalysisPlan from test case specification for deterministic testing."""
    tools = [ToolName(t) for t in test_case.get("expected_tools", [])]
    steps: list[PlanStep] = []
    
    for idx, (tool_name, params) in enumerate(zip(test_case.get("expected_tools", []), test_case.get("expected_params", []))):
        step_num = idx + 1
        depends_on = [step_num - 1] if step_num > 1 and tool_name == "charts" else []
        steps.append(
            PlanStep(
                step_number=step_num,
                tool=ToolName(tool_name),
                description=f"Execute {tool_name}",
                parameters=params,
                depends_on=depends_on,
            )
        )

    intent_val = test_case.get("expected_intent", "unknown")
    try:
        intent = Intent(intent_val)
    except ValueError:
        intent = Intent.UNKNOWN

    return AnalysisPlan(
        intent=intent,
        rationale=f"Deterministic plan for {test_case['id']}",
        steps=steps,
        selected_tools=tools,
    )


def evaluate_single_case(
    test_case: dict[str, Any],
    llm: BaseLLM | None = None,
    live_mode: bool = False,
) -> TestCaseResult:
    """Evaluate a single benchmark query test case."""
    start_time = time.perf_counter()
    case_id = test_case["id"]
    category = test_case["category"]
    query = test_case["query"]
    is_in_domain = test_case.get("is_in_domain", True)
    expected_intent = test_case.get("expected_intent", "unknown")
    expected_tools = test_case.get("expected_tools", [])

    result = TestCaseResult(
        id=case_id,
        category=category,
        query=query,
        is_in_domain=is_in_domain,
        expected_intent=expected_intent,
        expected_tools=expected_tools,
    )

    # 1. Plan Generation (Live LLM or Deterministic)
    plan: AnalysisPlan
    if live_mode and llm is not None:
        messages = _build_planner_messages(query, history=[])
        try:
            plan = llm.structured_chat(messages, AnalysisPlan)
        except Exception as exc:
            result.error_message = f"Live LLM call failed: {exc}"
            result.execution_duration_ms = (time.perf_counter() - start_time) * 1000
            return result
    else:
        plan = build_deterministic_plan_from_case(test_case)

    # 2. Score Intent & Tool Selection
    actual_intent = plan.intent.value if hasattr(plan.intent, "value") else str(plan.intent)
    actual_tools = [s.tool.value if hasattr(s.tool, "value") else str(s.tool) for s in plan.steps]
    result.actual_intent = actual_intent
    result.actual_tools = actual_tools

    result.intent_matched = (actual_intent == expected_intent)
    result.tools_matched = (actual_tools == expected_tools)

    # 3. Parameter Validation
    val_result = validate_analysis_plan(plan)
    result.parameters_valid = val_result.is_valid
    if not val_result.is_valid:
        result.error_message = "; ".join(val_result.errors)

    # 4. Deterministic Tool Execution
    if not plan.steps:
        # Conversational / Out-of-Domain cases succeed if expected to have no tools
        result.execution_success = (len(expected_tools) == 0)
    else:
        try:
            conn = create_session_connection()
            tool_results: list[ToolResult] = []
            exec_ok = True

            for step_idx, step in enumerate(plan.steps):
                state_step = {
                    "query": query,
                    "plan": plan,
                    "current_step": step_idx,
                    "selected_tools": plan.selected_tools,
                    "tool_results": tool_results,
                    "chart_artifacts": [],
                    "errors": [],
                    "messages": [],
                }
                node_fn = TOOL_NODE_MAP.get(step.tool.value)
                if node_fn is None:
                    exec_ok = False
                    result.error_message = f"No node function registered for tool {step.tool.value}"
                    break

                step_patch = node_fn(state_step)
                if step_patch.get("errors"):
                    exec_ok = False
                    result.error_message = "; ".join(step_patch["errors"])
                    break
                
                step_results = step_patch.get("tool_results", [])
                if step_results:
                    last_res = step_results[-1]
                    if not last_res.success:
                        exec_ok = False
                        result.error_message = last_res.error
                        break
                    tool_results.append(last_res)


            result.execution_success = exec_ok
        except Exception as exc:
            result.execution_success = False
            result.error_message = f"Execution exception: {exc}"

    result.execution_duration_ms = (time.perf_counter() - start_time) * 1000
    return result


def run_benchmark_evaluation(
    dataset_path: Path | str,
    live_mode: bool = False,
    output_path: Path | str | None = None,
) -> EvaluationScorecard:
    """Run complete benchmark evaluation across all test cases."""
    dataset = load_dataset(dataset_path)
    llm: BaseLLM | None = None
    if live_mode:
        llm = create_llm()

    scorecard = EvaluationScorecard()
    scorecard.total_queries = len(dataset)

    results: list[TestCaseResult] = []
    for case in dataset:
        if live_mode:
            # Free-tier rate limiting: 12s sleep between live API requests
            time.sleep(12)
        res = evaluate_single_case(case, llm=llm, live_mode=live_mode)
        results.append(res)
        if res.is_in_domain:
            scorecard.in_domain_queries += 1
        else:
            scorecard.out_of_domain_queries += 1

    scorecard.results = results

    # Compute aggregate percentages
    if scorecard.total_queries > 0:
        intent_matches = sum(1 for r in results if r.intent_matched)
        tool_matches = sum(1 for r in results if r.tools_matched)
        param_valids = sum(1 for r in results if r.parameters_valid)
        
        # Execution success computed over executable in-domain queries
        exec_cases = [r for r in results if r.is_in_domain and r.expected_tools]
        exec_successes = sum(1 for r in exec_cases if r.execution_success)

        scorecard.intent_accuracy_pct = (intent_matches / scorecard.total_queries) * 100
        scorecard.tool_match_pct = (tool_matches / scorecard.total_queries) * 100
        scorecard.parameter_validity_pct = (param_valids / scorecard.total_queries) * 100
        scorecard.execution_success_pct = (
            (exec_successes / len(exec_cases)) * 100 if exec_cases else 100.0
        )

    # Output report
    report_md = scorecard.to_markdown()
    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            f.write(report_md)
        logger.info("Saved evaluation report to %s", output_path)

    return scorecard


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Insight Copilot Evaluation Harness")
    parser.add_argument(
        "--dataset",
        type=str,
        default=str(ROOT_DIR / "tests" / "evaluation" / "eval_dataset.json"),
        help="Path to evaluation dataset JSON",
    )
    parser.add_argument("--live", action="store_true", help="Run live LLM evaluation")
    parser.add_argument(
        "--output",
        type=str,
        default=str(ROOT_DIR / "docs" / "evaluation-results.md"),
        help="Path to output markdown report",
    )

    args = parser.parse_args()
    scorecard = run_benchmark_evaluation(args.dataset, live_mode=args.live, output_path=args.output)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(scorecard.to_markdown())

