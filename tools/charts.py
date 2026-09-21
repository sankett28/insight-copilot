"""
tools/charts.py
---------------
Charts tool — renders Plotly visualisations from pre-computed tabular data.

Design contract:
  - Chart data comes exclusively from a preceding tool (data_query, metrics,
    trends).  This tool never queries the database itself.
  - The LLM does not choose chart parameters; chart type and axes are derived
    deterministically from the plan.
  - Output is a Plotly figure serialised to dict (fig.to_dict()) stored in
    state["chart_artifacts"] for the UI to render.

Current status: PLACEHOLDER — returns a stub result.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from agent.state import AgentState
from models.schemas import ToolName, ToolResult

logger = logging.getLogger(__name__)


class ChartType(str, Enum):
    """Supported Plotly chart types."""

    BAR = "bar"
    LINE = "line"
    SCATTER = "scatter"
    PIE = "pie"
    AREA = "area"
    HEATMAP = "heatmap"


def charts_tool_node(state: AgentState) -> dict:
    """LangGraph node: generate a Plotly chart from existing tool results.

    Reads:
        state["tool_results"] — to find the data produced by a preceding tool
        state["plan"]         — to extract chart configuration
        state["current_step"] — to identify the correct plan step

    Writes:
        tool_results     — appends a ToolResult containing the figure dict
        chart_artifacts  — appends the raw Plotly figure dict for UI rendering
    """
    step = state.get("current_step", 0)

    logger.info("charts_tool_node: executing step %d", step)

    # TODO: Find the most recent successful ToolResult, extract .data, and
    #       build a Plotly figure according to the plan's chart configuration.
    result = ToolResult(
        tool=ToolName.CHARTS,
        step_number=step + 1,
        success=False,
        data=None,
        error="charts tool not yet implemented — placeholder stub.",
    )

    return {"tool_results": [result]}


def render_chart(
    data: list[dict[str, Any]],
    chart_type: ChartType,
    x_column: str,
    y_column: str,
    color_column: str | None = None,
    title: str = "",
) -> dict[str, Any]:
    """Render a Plotly chart and return it as a serialisable dict.

    Args:
        data:         List of row dicts (output from a data/metrics/trends tool).
        chart_type:   Type of chart to render.
        x_column:     Column to use for the x-axis.
        y_column:     Column to use for the y-axis.
        color_column: Optional column for colour grouping.
        title:        Chart title.

    Returns:
        Plotly figure serialised as a dict (``fig.to_dict()``).

    Raises:
        NotImplementedError: Until the chart rendering logic is implemented.
    """
    raise NotImplementedError("charts tool not yet implemented.")
