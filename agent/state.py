"""
agent/state.py
--------------
Defines AgentState — the single shared-memory object that flows through
every node in the LangGraph StateGraph.

Design decisions:
- Uses TypedDict (required by LangGraph) rather than Pydantic BaseModel.
- Every field is Optional with a documented default so nodes can add data
  incrementally without having to initialise the full state up-front.
- Fields use LangGraph's `Annotated` + `operator.add` reducer only where
  *accumulation* is semantically correct (messages, tool_results, errors).
  All other fields are plain last-write-wins.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any

from typing_extensions import TypedDict

from models.schemas import AnalysisPlan, Message, ToolName, ToolResult


class AgentState(TypedDict, total=False):
    """Shared state for the Insight Copilot LangGraph graph.

    total=False means every key is Optional at the TypedDict level,
    allowing nodes to write only the fields they own.
    """

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------
    messages: Annotated[list[Message], operator.add]
    """Full conversation history, accumulated across turns.

    Uses the `operator.add` reducer so each node can *append* messages
    without overwriting earlier ones.
    """

    # ------------------------------------------------------------------
    # Current turn
    # ------------------------------------------------------------------
    query: str
    """The raw natural-language question submitted by the user this turn."""

    # ------------------------------------------------------------------
    # Planning outputs
    # ------------------------------------------------------------------
    intent: str
    """Classified intent string (mirrors Intent enum value), set by the planner."""

    plan: AnalysisPlan | None
    """Structured execution plan produced by the planner node.
    None until the planner has run.
    """

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------
    selected_tools: list[ToolName]
    """Ordered list of tools the router will invoke, derived from plan.steps."""

    current_step: int
    """Index into selected_tools indicating the next tool to execute.
    Starts at 0; the router increments it after dispatching each tool.
    """

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------
    tool_results: Annotated[list[ToolResult], operator.add]
    """Accumulated results from every tool invocation this turn.

    Uses operator.add so results from sequential tool calls are collected
    without overwriting earlier results.
    """

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------
    chart_artifacts: list[dict[str, Any]]
    """List of Plotly figure dicts (fig.to_dict()) produced by the charts tool.
    Stored separately so the UI can render them independently of the text answer.
    """

    # ------------------------------------------------------------------
    # Final output
    # ------------------------------------------------------------------
    final_answer: str | None
    """Analyst-style natural-language answer produced by the synthesizer.
    None until the synthesizer has run.
    """

    # ------------------------------------------------------------------
    # Error tracking
    # ------------------------------------------------------------------
    errors: Annotated[list[str], operator.add]
    """Accumulated error messages from any node or tool that encountered a problem.

    Uses operator.add so multiple errors are collected rather than overwritten.
    An empty list means no errors occurred.
    """
