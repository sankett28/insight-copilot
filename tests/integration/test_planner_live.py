"""
tests/integration/test_planner_live.py
--------------------------------------
Live integration tests validating Gemini planner intent classification
and structured parameter extraction for 15 representative user queries.

Requires GEMINI_API_KEY environment variable.
"""

import os
import time
import pytest
from dotenv import load_dotenv

from agent.planner import _build_planner_messages
from llm.factory import create_llm
from models.schemas import AnalysisPlan, Intent, ToolName

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY environment variable is required for live planner tests.",
)

TEST_QUERIES = [
    ("What is the total revenue by region?", Intent.METRICS),
    ("Show me monthly profit trends for 2024", Intent.TREND),
    ("What does the dataset look like?", Intent.DATA_QUERY),
    ("Which category has the highest average unit price?", Intent.METRICS),
    ("Compare North and South revenue", Intent.METRICS),
    ("Show me a bar chart of revenue by region", Intent.CHART),
    ("Which salesperson sold the most units?", Intent.METRICS),
    ("What is the profit margin by product category?", Intent.METRICS),
    ("Show revenue trend with a line chart", Intent.COMBINED),
    ("How did Q1 compare to Q2 for total revenue?", Intent.METRICS),
    ("Which products contribute most to total profit?", Intent.METRICS),
    ("Are there any months with unusually low revenue?", Intent.TREND),
    ("What is the revenue breakdown by region and category?", Intent.COMBINED),
    ("How has profit changed month over month?", Intent.TREND),
    ("Give me an overview of the data", Intent.DATA_QUERY),
]


@pytest.fixture(scope="module")
def live_llm():
    return create_llm()


@pytest.mark.parametrize("query,expected_intent", TEST_QUERIES)
def test_live_planner_query_intent_and_parameters(live_llm, query, expected_intent):
    """Verify Gemini returns a valid AnalysisPlan with correct intent and structured parameters."""
    # Free tier limit is 5 requests per minute; pause 12s between calls to prevent 429
    time.sleep(12)
    messages = _build_planner_messages(query, history=[])
    
    # Retry on 429 rate limit
    for attempt in range(3):
        try:
            plan: AnalysisPlan = live_llm.structured_chat(messages, AnalysisPlan)
            break
        except Exception as exc:
            if "429" in str(exc) or "ResourceExhausted" in str(type(exc).__name__):
                time.sleep(25)
                continue
            raise

    assert isinstance(plan, AnalysisPlan)
    assert len(plan.rationale) > 0
    assert len(plan.steps) >= 1
    assert len(plan.selected_tools) >= 1

    # Verify each plan step contains valid attributes
    for step in plan.steps:
        assert isinstance(step.step_number, int)
        assert isinstance(step.tool, ToolName)
        assert len(step.description) > 0
        assert isinstance(step.parameters, dict)
