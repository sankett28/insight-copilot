"""
tools/trends.py
---------------
Trends tool — analyses a numeric measure over time or across an ordered
dimension using DuckDB window functions.

Design contract:
  - Trend calculations (rolling averages, period-over-period change, etc.)
    are executed in DuckDB, not estimated by the LLM.
  - Results are tabular (list of dicts) — the charts tool renders them visually.

Current status: PLACEHOLDER — returns a stub result.
"""

from __future__ import annotations

import logging
from enum import Enum

from agent.state import AgentState
from models.schemas import ToolName, ToolResult

logger = logging.getLogger(__name__)


class TrendType(str, Enum):
    """Supported trend analysis types."""

    TIME_SERIES = "time_series"
    """Aggregate a measure by a date/time column."""

    ROLLING_AVERAGE = "rolling_average"
    """Compute a rolling (moving) average over a window of periods."""

    PERIOD_OVER_PERIOD = "period_over_period"
    """Compute absolute and percentage change between consecutive periods."""

    CUMULATIVE = "cumulative"
    """Running cumulative sum of a measure over time."""


def trends_tool_node(state: AgentState) -> dict:
    """LangGraph node: perform trend analysis on the dataset.

    Reads:
        state["plan"]         — to extract trend parameters
        state["current_step"] — to identify the correct plan step

    Writes:
        tool_results — appends a ToolResult (success or error)
    """
    step = state.get("current_step", 0)

    logger.info("trends_tool_node: executing step %d", step)

    # TODO: Extract trend parameters from plan.steps[step] and run DuckDB analysis.
    result = ToolResult(
        tool=ToolName.TRENDS,
        step_number=step + 1,
        success=False,
        data=None,
        error="trends tool not yet implemented — placeholder stub.",
    )

    return {"tool_results": [result]}


def compute_trend(
    table: str,
    measure_column: str,
    time_column: str,
    trend_type: TrendType = TrendType.TIME_SERIES,
    group_by: list[str] | None = None,
    filters: dict[str, object] | None = None,
    window_size: int = 3,
) -> list[dict]:
    """Compute a trend analysis via DuckDB.

    Args:
        table:          Source table/view name.
        measure_column: Numeric column to analyse.
        time_column:    Date/time column to order by.
        trend_type:     Type of trend analysis to perform.
        group_by:       Optional grouping dimensions (e.g., category, region).
        filters:        Column-to-value equality filters applied before analysis.
        window_size:    Number of periods for rolling calculations.

    Returns:
        List of row dicts with time labels and computed trend values.

    Raises:
        NotImplementedError: Until the data layer is ready.
    """
    raise NotImplementedError("trends tool not yet implemented.")
