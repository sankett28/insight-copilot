"""
tests/test_synthesizer.py
-------------------------
Unit tests for the synthesizer node: evidence formatting, provenance headers,
bounded history windowing, prompt construction, and error fallbacks.
"""

from typing import Type
from pydantic import BaseModel

from agent.state import AgentState, create_initial_state
from agent.synthesizer import (
    _build_output,
    _build_synthesizer_messages,
    _format_tool_results,
    build_synthesizer_node,
)
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


class RecordingMockLLM(BaseLLM):
    """Mock LLM that records received messages and returns configurable content."""

    def __init__(self, response_text: str = "Synthesized answer [Step 1].", should_raise: bool = False):
        self.response_text = response_text
        self.should_raise = should_raise
        self.last_messages: list[dict[str, str]] = []

    @property
    def model_name(self) -> str:
        return "recording-mock"

    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.0, max_tokens: int | None = None) -> LLMResponse:
        self.last_messages = messages
        if self.should_raise:
            raise RuntimeError("LLM API call timed out")
        return LLMResponse(content=self.response_text)

    def structured_chat(
        self,
        messages: list[dict[str, str]],
        schema: Type[BaseModel],
        *,
        temperature: float = 0.0,
    ) -> BaseModel:
        raise NotImplementedError()


def test_format_tool_results_empty():
    """Empty tool results should return descriptive fallback string."""
    assert _format_tool_results([]) == "No tool results available."


def test_format_tool_results_provenance_and_header():
    """ToolResult formatting must include step number, tool name, provenance metrics, and data."""
    result = ToolResult(
        step_number=1,
        tool=ToolName.METRICS,
        success=True,
        data=[{"Category": "Electronics", "Revenue": 150000.0}],
        source_view="dataset",
        row_count=1,
        execution_time_ms=4.5,
    )
    formatted = _format_tool_results([result])
    assert "[Step 1 | metrics] ✓ (source: dataset, rows: 1, time: 4.5ms)" in formatted
    assert '"Category": "Electronics"' in formatted
    assert "150000.0" in formatted


def test_format_tool_results_truncation():
    """Tabular list outputs with >15 items should be truncated with a clear count indicator."""
    long_data = [{"id": i, "val": i * 10} for i in range(30)]
    result = ToolResult(
        step_number=2,
        tool=ToolName.DATA_QUERY,
        success=True,
        data=long_data,
        source_view="dataset",
        row_count=30,
        execution_time_ms=12.1,
    )
    formatted = _format_tool_results([result])
    assert "(Showing first 15 of 30 rows)" in formatted
    assert '"id": 0' in formatted
    assert '"id": 14' in formatted
    assert '"id": 20' not in formatted


def test_build_synthesizer_messages_bounded_history():
    """Synthesizer messages should bound prior history to the last 10 messages."""
    # Create 15 prior turns
    history: list[Message] = []
    for i in range(15):
        history.append(Message(role=Role.USER, content=f"User Q{i}"))
        history.append(Message(role=Role.ASSISTANT, content=f"Assistant A{i}"))

    state = create_initial_state("Current Query", history=history)
    tool_results = [
        ToolResult(
            step_number=1,
            tool=ToolName.METRICS,
            success=True,
            data={"total_revenue": 500000},
        )
    ]

    messages = _build_synthesizer_messages("Current Query", tool_results, state)

    # First message is system prompt
    assert messages[0]["role"] == "system"

    # History should be bounded to at most 10 messages + system prompt + final user prompt
    # In this case: 1 system + 10 history + 1 current prompt = 12 total messages
    assert len(messages) == 12
    # The oldest history message in the payload should be Q10 (since 10 items from 30 items)
    assert "Assistant A14" in messages[-2]["content"]
    assert "Current Query" in messages[-1]["content"]


def test_synthesizer_node_error_fallback():
    """When errors exist with no tool results, synthesizer returns a safe error message without LLM call."""
    llm = RecordingMockLLM()
    synthesizer = build_synthesizer_node(llm)

    state: AgentState = {
        "query": "Invalid query",
        "errors": ["Column 'Unknown' does not exist in dataset"],
        "tool_results": [],
        "messages": [Message(role=Role.USER, content="Invalid query")],
    }

    patch = synthesizer(state)
    assert len(llm.last_messages) == 0  # LLM was not called
    assert "I encountered an error while processing your request" in patch["final_answer"]
    assert "Column 'Unknown' does not exist" in patch["final_answer"]
    assert len(patch["messages"]) == 2


def test_synthesizer_node_llm_exception_fallback():
    """When LLM call fails, synthesizer catches exception and returns graceful error message."""
    llm = RecordingMockLLM(should_raise=True)
    synthesizer = build_synthesizer_node(llm)

    state = create_initial_state("What is total revenue?")
    state["tool_results"] = [
        ToolResult(step_number=1, tool=ToolName.METRICS, success=True, data={"Revenue": 100000})
    ]

    patch = synthesizer(state)
    assert "unable to generate a response due to an internal error" in patch["final_answer"]
    assert len(patch["messages"]) == 2
    assert patch["messages"][-1].content == patch["final_answer"]


def test_synthesizer_node_success():
    """Successful synthesis executes LLM chat and appends assistant answer to state messages."""
    expected_text = "Total revenue across all regions in 2024 was $1,250,000 [Step 1]."
    llm = RecordingMockLLM(response_text=expected_text)
    synthesizer = build_synthesizer_node(llm)

    plan = AnalysisPlan(
        intent=Intent.METRICS,
        rationale="Compute total 2024 sales revenue",
        steps=[PlanStep(step_number=1, tool=ToolName.METRICS, description="Total revenue", parameters={"metric": "Revenue"})],
        selected_tools=[ToolName.METRICS],
    )

    state = create_initial_state("What is total revenue?")
    state["plan"] = plan
    state["tool_results"] = [
        ToolResult(
            step_number=1,
            tool=ToolName.METRICS,
            success=True,
            data={"total_revenue": 1250000.0},
            source_view="dataset",
            row_count=1,
            execution_time_ms=3.8,
        )
    ]

    patch = synthesizer(state)
    assert patch["final_answer"] == expected_text
    assert len(patch["messages"]) == 2
    assert patch["messages"][-1].role == Role.ASSISTANT
    assert patch["messages"][-1].content == expected_text
