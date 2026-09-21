"""
tests/test_graph.py
--------------------
Integration tests for the LangGraph StateGraph pipeline using a MockLLM.
Tests MUST NOT require a live Gemini API call.
"""

from typing import Type
from pydantic import BaseModel

from agent.graph import build_graph
from agent.state import AgentState, create_initial_state
from llm.base import BaseLLM, LLMResponse
from models.schemas import (
    AnalysisPlan,
    Intent,
    Message,
    PlanStep,
    Role,
    ToolName,
    ToolResult,
)


class MockLLM(BaseLLM):
    """Deterministic Mock LLM for offline graph testing."""

    def __init__(self, plan_to_return: AnalysisPlan, chat_response: str = "Mock analysis result"):
        self.plan_to_return = plan_to_return
        self.chat_response = chat_response

    @property
    def model_name(self) -> str:
        return "mock-model"

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.0) -> LLMResponse:
        return LLMResponse(content=self.chat_response)

    def structured_chat(
        self,
        messages: list[dict[str, str]],
        schema: Type[BaseModel],
        temperature: float = 0.0,
    ) -> BaseModel:
        if schema == AnalysisPlan:
            return self.plan_to_return
        raise ValueError(f"Unsupported schema {schema}")



def test_graph_single_tool_execution():
    """Test graph execution for a single-tool metrics query."""
    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Category revenue comparison",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.METRICS,
                description="Category revenue",
                parameters={"metric": "Revenue", "aggregation": "sum", "group_by": "Category"},
            )
        ],
        selected_tools=[ToolName.METRICS],
    )
    llm = MockLLM(plan_to_return=plan, chat_response="Total revenue is highest in Electronics.")
    graph = build_graph(llm)

    initial_state = create_initial_state("Which category generated the most revenue?")
    result_state = graph.invoke(initial_state)

    assert result_state["final_answer"] == "Total revenue is highest in Electronics."
    assert len(result_state["tool_results"]) == 1
    assert result_state["tool_results"][0].success is True
    assert result_state["current_step"] == 1


def test_graph_multi_tool_execution():
    """Test graph execution for a 2-step plan (trends -> charts)."""
    plan = AnalysisPlan(
        intent=Intent.COMBINED,
        rationale="Monthly trend and line chart visualization",
        steps=[
            PlanStep(
                step_number=1,
                tool=ToolName.TRENDS,
                description="Calculate monthly revenue trend",
                parameters={"metric": "Revenue", "date_column": "Date", "granularity": "month"},
                depends_on=[],
            ),
            PlanStep(
                step_number=2,
                tool=ToolName.CHARTS,
                description="Visualize trend as line chart",
                parameters={"chart_type": "line", "x": "period", "y": "total_revenue"},
                depends_on=[1],
            ),
        ],
        selected_tools=[ToolName.TRENDS, ToolName.CHARTS],
    )

    llm = MockLLM(plan_to_return=plan, chat_response="Revenue fluctuated across 2024 as shown in the chart.")
    graph = build_graph(llm)

    initial_state = create_initial_state("Show me monthly revenue trend and visualize it")
    result_state = graph.invoke(initial_state)

    assert result_state["final_answer"] == "Revenue fluctuated across 2024 as shown in the chart."
    assert len(result_state["tool_results"]) == 2
    assert len(result_state["chart_artifacts"]) == 1
    assert result_state["tool_results"][0].tool == ToolName.TRENDS
    assert result_state["tool_results"][1].tool == ToolName.CHARTS


def test_state_isolation_between_turns():
    """Verify that create_initial_state resets execution state between turns."""
    history = [
        Message(role=Role.USER, content="Which category generated the most revenue?"),
        Message(role=Role.ASSISTANT, content="Electronics had highest revenue."),
    ]

    # Initialize Turn 2 state
    turn2_state = create_initial_state("What about profit?", history=history)

    assert len(turn2_state["messages"]) == 3  # 2 history + 1 new user query
    assert turn2_state["query"] == "What about profit?"
    assert turn2_state["current_step"] == 0
    assert turn2_state["tool_results"] == []
    assert turn2_state["chart_artifacts"] == []
    assert turn2_state["final_answer"] is None
    assert turn2_state["errors"] == []
    assert turn2_state["plan"] is None
