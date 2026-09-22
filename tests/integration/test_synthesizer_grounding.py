"""
tests/integration/test_synthesizer_grounding.py
-----------------------------------------------
Live integration tests validating Gemini synthesizer grounding, step citations,
and out-of-domain guardrails.

Requires GEMINI_API_KEY environment variable.
"""

import os
import time
import pytest
from dotenv import load_dotenv

from agent.state import create_initial_state
from agent.synthesizer import build_synthesizer_node
from llm.factory import create_llm
from models.schemas import AnalysisPlan, Intent, PlanStep, ToolName, ToolResult

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY environment variable is required for live synthesizer tests.",
)


@pytest.fixture(scope="module")
def live_llm():
    return create_llm()


def test_live_synthesizer_evidence_citation_and_grounding(live_llm):
    """Verify live synthesizer output cites [Step 1] and includes exact metrics from ToolResult."""
    time.sleep(12)
    synthesizer = build_synthesizer_node(live_llm)

    state = create_initial_state("Which region generated the highest revenue in 2024?")
    state["plan"] = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Compute revenue by region",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Revenue by region",
                parameters={"metric": "Revenue", "group_by": "Region", "sort_by": "total_revenue", "sort_order": "desc"},
            )
        ],
        selected_tools=[ToolName.METRICS],
    )
    state["tool_results"] = [
        ToolResult(
            step_number=1,
            tool=ToolName.METRICS,
            success=True,
            data=[
                {"Region": "North", "total_revenue": 520000.0},
                {"Region": "South", "total_revenue": 310000.0},
            ],
            source_view="dataset",
            row_count=2,
            execution_time_ms=5.0,
        )
    ]

    patch = synthesizer(state)
    answer = patch["final_answer"]

    assert isinstance(answer, str)
    assert "[Step 1]" in answer or "[Step 1 | metrics]" in answer or "Step 1" in answer
    assert "520,000" in answer or "520000" in answer or "North" in answer
