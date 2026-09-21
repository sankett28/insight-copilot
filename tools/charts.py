"""
tools/charts.py
---------------
Charts tool — renders Plotly visualisations from pre-computed tabular data.

Design contract:
  - Chart data comes exclusively from a preceding tool (data_query, metrics, trends).
  - Never queries database directly.
  - Output is a Plotly figure serialised to dict (fig.to_dict()) stored in
    state["chart_artifacts"] and ToolResult.data.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import plotly.express as px

from agent.state import AgentState
from models.schemas import ChartRequest, ToolName, ToolResult

logger = logging.getLogger(__name__)


def charts_tool_node(state: AgentState) -> dict:
    """LangGraph node: generate a Plotly chart from existing tool results.

    Reads:
        state["tool_results"] — data produced by a preceding tool
        state["plan"]         — to extract chart configuration
        state["current_step"] — index of the active plan step

    Writes:
        tool_results     — appends a ToolResult containing the figure dict
        chart_artifacts  — appends the raw Plotly figure dict for UI rendering
    """
    step_idx = state.get("current_step", 0)
    plan = state.get("plan")
    tool_results = state.get("tool_results", [])

    existing_results = list(tool_results)

    if not plan or step_idx >= len(plan.steps):
        err_msg = f"Charts tool failed: plan missing or step index {step_idx} out of range."
        existing_results.append(
            ToolResult(
                tool=ToolName.CHARTS,
                step_number=step_idx + 1,
                success=False,
                data=None,
                error=err_msg,
            )
        )
        return {"tool_results": existing_results}

    plan_step = plan.steps[step_idx]
    raw_params = plan_step.parameters or {}

    # Find candidate source tool results (from depends_on or latest preceding tool result)
    source_result: ToolResult | None = None
    if plan_step.depends_on:
        dep_step_num = plan_step.depends_on[0]
        for tr in tool_results:
            if tr.step_number == dep_step_num and tr.success and tr.data:
                source_result = tr
                break

    if source_result is None:
        # Fallback to the most recent successful tool result with list data
        for tr in reversed(tool_results):
            if tr.success and isinstance(tr.data, list) and len(tr.data) > 0:
                source_result = tr
                break

    if not source_result or not isinstance(source_result.data, list) or len(source_result.data) == 0:
        err_msg = "Charts tool failed: No valid preceding tabular data available to plot."
        existing_results.append(
            ToolResult(
                tool=ToolName.CHARTS,
                step_number=plan_step.step_number,
                success=False,
                data=None,
                error=err_msg,
            )
        )
        return {"tool_results": existing_results}


    try:
        # Infer default x and y columns if missing from parameters
        rows: list[dict[str, Any]] = source_result.data
        df_sample = pd.DataFrame(rows)
        cols = df_sample.columns.tolist()

        # Smart column resolution: match requested x and y against actual DataFrame columns
        x_req = str(raw_params.get("x", "")).lower()
        y_req = str(raw_params.get("y", "")).lower()

        matched_x = None
        matched_y = None

        for col in cols:
            col_lower = col.lower()
            if x_req and (x_req == col_lower or x_req in col_lower or col_lower in x_req):
                matched_x = col
            if y_req and (y_req == col_lower or y_req in col_lower or col_lower in y_req):
                matched_y = col

        x_col = matched_x or (cols[0] if len(cols) >= 1 else None)
        y_col = matched_y or (cols[1] if len(cols) >= 2 else cols[0] if len(cols) >= 1 else None)

        chart_type = raw_params.get("chart_type", "bar")
        title = raw_params.get("title", f"{y_col} by {x_col}")

        req = ChartRequest(
            chart_type=chart_type,
            x=str(x_col),
            y=str(y_col),
            color=raw_params.get("color"),
            title=title,
        )

        fig_dict = render_chart_from_data(rows, req)

        existing_results = list(tool_results)
        existing_results.append(
            ToolResult(
                tool=ToolName.CHARTS,
                step_number=plan_step.step_number,
                success=True,
                data=fig_dict,
                error=None,
            )
        )

        existing_artifacts = list(state.get("chart_artifacts", []))
        existing_artifacts.append(fig_dict)

        return {
            "tool_results": existing_results,
            "chart_artifacts": existing_artifacts,
        }

    except Exception as exc:  # noqa: BLE001
        logger.exception("Charts tool execution error: %s", exc)
        existing_results = list(tool_results)
        existing_results.append(
            ToolResult(
                tool=ToolName.CHARTS,
                step_number=plan_step.step_number,
                success=False,
                data=None,
                error=f"Charts rendering error: {exc}",
            )
        )
        return {"tool_results": existing_results}



def render_chart_from_data(
    data: list[dict[str, Any]],
    req: ChartRequest,
) -> dict[str, Any]:
    """Render a Plotly figure and return fig.to_dict()."""
    df = pd.DataFrame(data)

    if req.chart_type == "bar":
        fig = px.bar(
            df,
            x=req.x,
            y=req.y,
            color=req.color,
            title=req.title,
            template="plotly_dark",
        )
    elif req.chart_type == "line":
        fig = px.line(
            df,
            x=req.x,
            y=req.y,
            color=req.color,
            title=req.title,
            template="plotly_dark",
        )
    elif req.chart_type == "scatter":
        fig = px.scatter(
            df,
            x=req.x,
            y=req.y,
            color=req.color,
            title=req.title,
            template="plotly_dark",
        )
    else:
        fig = px.bar(
            df,
            x=req.x,
            y=req.y,
            color=req.color,
            title=req.title,
            template="plotly_dark",
        )

    fig.update_layout(margin={"l": 40, "r": 40, "t": 50, "b": 40})
    return fig.to_dict()

