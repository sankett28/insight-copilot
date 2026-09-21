"""
tools/metrics.py
----------------
Metrics tool — computes aggregated numeric metrics (sums, averages, counts,
rankings, percentiles) from the dataset using DuckDB.

Design contract:
  - All calculations are performed by DuckDB, not by the LLM.
  - The LLM receives only the *result* via the synthesizer.
  - Metric definitions are parameterised; no hard-coded business logic.

Current status: PLACEHOLDER — returns a stub result.
"""

from __future__ import annotations

import logging
from enum import Enum

from agent.state import AgentState
from models.schemas import ToolName, ToolResult

logger = logging.getLogger(__name__)


class AggregationType(str, Enum):
    """Supported aggregation operations."""

    SUM = "sum"
    AVG = "avg"
    COUNT = "count"
    MIN = "min"
    MAX = "max"
    MEDIAN = "median"


def metrics_tool_node(state: AgentState) -> dict:
    """LangGraph node: compute aggregated metrics from the dataset.

    Reads:
        state["plan"]         — to extract metric parameters
        state["current_step"] — to identify the correct plan step

    Writes:
        tool_results — appends a ToolResult (success or error)
    """
    step = state.get("current_step", 0)

    logger.info("metrics_tool_node: executing step %d", step)

    # TODO: Extract metric parameters from plan.steps[step] and run DuckDB aggregation.
    result = ToolResult(
        tool=ToolName.METRICS,
        step_number=step + 1,
        success=False,
        data=None,
        error="metrics tool not yet implemented — placeholder stub.",
    )

    return {"tool_results": [result]}


def compute_metric(
    table: str,
    metric_column: str,
    aggregation: AggregationType,
    group_by: list[str] | None = None,
    filters: dict[str, object] | None = None,
    top_n: int | None = None,
) -> list[dict]:
    """Compute an aggregated metric via DuckDB.

    Args:
        table:         Source table/view name.
        metric_column: Column to aggregate.
        aggregation:   Aggregation function to apply.
        group_by:      Columns to group by; None means no grouping.
        filters:       Column-to-value equality filters applied before aggregation.
        top_n:         If set, return only the top N rows ordered by the metric descending.

    Returns:
        List of row dicts with group keys and the aggregated value.

    Raises:
        NotImplementedError: Until the data layer is ready.
    """
    raise NotImplementedError("metrics tool not yet implemented.")
