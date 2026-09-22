"""
agent/state.py
--------------
Defines AgentState — the single shared-memory object that flows through
every node in the LangGraph StateGraph.

Design decisions:
- Uses TypedDict (required by LangGraph) rather than Pydantic BaseModel.
- Explicitly separates persistent conversation state (messages) from
  per-turn execution state (query, plan, selected_tools, current_step,
  tool_results, chart_artifacts, final_answer, errors).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any

from typing_extensions import TypedDict

from models.schemas import AnalysisPlan, Message, Role, ToolName, ToolResult


class AgentState(TypedDict, total=False):
    """Shared state for the Insight Copilot LangGraph graph."""

    # ------------------------------------------------------------------
    # Persistent conversation state
    # ------------------------------------------------------------------
    messages: list[Message]
    """Full conversation history, accumulated across turns."""

    # ------------------------------------------------------------------
    # Per-turn execution state
    # ------------------------------------------------------------------
    query: str
    """The raw natural-language question submitted by the user this turn."""

    intent: str
    """Classified intent string, set by the planner."""

    plan: AnalysisPlan | None
    """Structured execution plan produced by the planner node."""

    selected_tools: list[ToolName]
    """Ordered list of tools the router will invoke, derived from plan.steps."""

    current_step: int
    """Index into selected_tools indicating the next tool step to execute (starts at 0)."""

    tool_results: list[ToolResult]
    """Accumulated results from tool invocations during this turn."""

    chart_artifacts: list[dict[str, Any]]
    """List of Plotly figure dicts (fig.to_dict()) produced by the charts tool this turn."""

    final_answer: str | None
    """Analyst-style natural-language answer produced by the synthesizer."""

    errors: list[str]
    """Accumulated error messages from any node or tool during this turn."""

    run_id: str
    """Unique identifier for this execution turn (UUID4)."""

    telemetry: dict[str, Any]
    """Structured telemetry metadata capturing execution durations and timings."""


def create_initial_state(
    query: str,
    history: list[Message] | None = None,
    run_id: str | None = None,
) -> AgentState:
    """Construct a clean AgentState for a new user query turn.

    Guarantees that previous-turn execution state (tool_results, chart_artifacts,
    current_step, errors, plan) does not leak into the new turn, while preserving
    the persistent conversation history.

    Args:
        query:   The new natural-language query from the user.
        history: Previous conversation messages (if any).
        run_id:  Optional execution run UUID string.

    Returns:
        A fresh AgentState dict with clean per-turn fields.
    """
    import time
    import uuid

    messages: list[Message] = list(history) if history else []
    messages.append(Message(role=Role.USER, content=query))
    turn_run_id = run_id or str(uuid.uuid4())

    return AgentState(
        messages=messages,
        query=query,
        run_id=turn_run_id,
        telemetry={
            "run_id": turn_run_id,
            "start_time": time.time(),
            "timings": {},
        },
        intent="",
        plan=None,
        selected_tools=[],
        current_step=0,
        tool_results=[],
        chart_artifacts=[],
        final_answer=None,
        errors=[],
    )


