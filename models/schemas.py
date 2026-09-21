"""
models/schemas.py
-----------------
Pydantic data contracts for Insight Copilot.

These schemas act as the authoritative definition of every structured object
that moves between components (planner → router → tools → synthesizer).
Keeping them in a dedicated module avoids circular imports and makes the
contracts easy to unit-test in isolation.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Intent(str, Enum):
    """High-level analytical intent inferred by the planner."""

    DATA_QUERY = "data_query"
    """Retrieve or filter raw rows from the dataset."""

    METRICS = "metrics"
    """Compute aggregated numeric metrics (sum, average, count, rank, etc.)."""

    TREND = "trend"
    """Analyse a value over time or across ordered categories."""

    CHART = "chart"
    """Generate a visualisation from pre-computed data."""

    COMBINED = "combined"
    """Multi-step plan that uses more than one analytical tool."""

    UNKNOWN = "unknown"
    """Intent could not be determined; the planner should ask for clarification."""


class ToolName(str, Enum):
    """Canonical names for every executable tool in the agent.

    Using an enum prevents typos and makes routing logic easy to test.
    """

    DATA_QUERY = "data_query"
    METRICS = "metrics"
    TRENDS = "trends"
    CHARTS = "charts"


# ---------------------------------------------------------------------------
# Execution plan
# ---------------------------------------------------------------------------


class PlanStep(BaseModel):
    """A single step in the execution plan."""

    step_number: int = Field(..., ge=1, description="1-based position in the plan.")
    tool: ToolName = Field(..., description="The tool to invoke at this step.")
    description: str = Field(
        ...,
        description="Human-readable description of what this step does.",
    )
    depends_on: list[int] = Field(
        default_factory=list,
        description=(
            "List of step_numbers that must complete before this step can run. "
            "Empty means this step can start immediately."
        ),
    )


class AnalysisPlan(BaseModel):
    """Structured plan produced by the Planner node.

    The plan is intentionally *visible*: it will be surfaced in the UI so
    the user can understand what the agent is about to do before it does it.

    The LLM produces this as structured output; no hidden chain-of-thought
    is stored here.
    """

    intent: Intent = Field(
        ...,
        description="Classified analytical intent of the user query.",
    )
    rationale: str = Field(
        ...,
        description=(
            "Short (≤3 sentences) plain-English explanation of why this plan "
            "was chosen.  This is the *only* reasoning exposed to the user."
        ),
    )
    steps: list[PlanStep] = Field(
        ...,
        min_length=1,
        description="Ordered list of execution steps.",
    )
    selected_tools: list[ToolName] = Field(
        ...,
        description="Flat list of tools referenced by this plan (may contain duplicates if a tool is used twice).",
    )


# ---------------------------------------------------------------------------
# Tool result
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    """Encapsulates the output of a single tool execution."""

    tool: ToolName = Field(..., description="Which tool produced this result.")
    step_number: int = Field(..., ge=1, description="Corresponding plan step.")
    success: bool = Field(..., description="Whether the tool completed without error.")
    data: Any = Field(
        default=None,
        description=(
            "Serialisable payload returned by the tool.  "
            "For data_query / metrics / trends this is typically a list of dicts. "
            "For charts this is a Plotly figure dict (fig.to_dict())."
        ),
    )
    error: str | None = Field(
        default=None,
        description="Error message if success=False, otherwise None.",
    )


# ---------------------------------------------------------------------------
# Conversation message
# ---------------------------------------------------------------------------


class Role(str, Enum):
    """Speaker role in the conversation history."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(BaseModel):
    """A single turn in the conversation."""

    role: Role
    content: str
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional bag for attaching structured data to a message (e.g., plan, tool trace).",
    )
