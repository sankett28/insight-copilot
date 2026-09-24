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
import time
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

    # Resolve cross-step sentinel placeholders before chart parameter usage
    from utils.result_resolver import resolve_step_parameters
    raw_params = resolve_step_parameters(raw_params, tool_results)

    # Find candidate source tool results with hierarchical priority:
    # 1. Tabular list data from declared dependencies
    # 2. Tabular list data from any preceding tool result
    # 3. Dict data from declared dependencies
    # 4. Dict data from any preceding tool result
    source_result: ToolResult | None = None
    if plan_step.depends_on:
        for dep_step_num in reversed(plan_step.depends_on):
            for tr in tool_results:
                if tr.step_number == dep_step_num and tr.success and isinstance(tr.data, list) and len(tr.data) > 0:
                    source_result = tr
                    break
            if source_result is not None:
                break

    if source_result is None:
        for tr in reversed(tool_results):
            if tr.success and isinstance(tr.data, list) and len(tr.data) > 0:
                source_result = tr
                break

    if source_result is None and plan_step.depends_on:
        for dep_step_num in reversed(plan_step.depends_on):
            for tr in tool_results:
                if tr.step_number == dep_step_num and tr.success and tr.data:
                    source_result = tr
                    break
            if source_result is not None:
                break

    if source_result is None:
        for tr in reversed(tool_results):
            if tr.success and tr.data:
                source_result = tr
                break

    if not source_result or not source_result.data:
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

    rows: list[dict[str, Any]] = []
    if isinstance(source_result.data, list):
        rows = [r for r in source_result.data if isinstance(r, dict)]
    elif isinstance(source_result.data, dict):
        if "records" in source_result.data and isinstance(source_result.data["records"], list):
            rows = source_result.data["records"]
        else:
            rows = [source_result.data]

    if not rows:
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

        start_t = time.perf_counter()
        req = ChartRequest(
            chart_type=chart_type,
            x=str(x_col),
            y=str(y_col),
            color=raw_params.get("color"),
            title=title,
        )

        fig_dict = render_chart_from_data(rows, req)
        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)

        existing_artifacts = list(state.get("chart_artifacts", []))
        chart_id = f"chart_{state.get('run_id', 'run')}_s{plan_step.step_number}_{len(existing_artifacts)}"
        fig_dict["_chart_id"] = chart_id
        fig_dict["_step_number"] = plan_step.step_number
        fig_dict["_run_id"] = state.get("run_id")

        existing_results = list(tool_results)
        existing_results.append(
            ToolResult(
                tool=ToolName.CHARTS,
                step_number=plan_step.step_number,
                success=True,
                data=fig_dict,
                error=None,
                source_view="tool_result",
                row_count=len(rows),
                execution_time_ms=duration_ms,
            )
        )

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
                source_view="tool_result",
            )
        )
        return {"tool_results": existing_results}



def render_chart_from_data(
    data: list[dict[str, Any]],
    req: ChartRequest,
) -> dict[str, Any]:
    """Render a Plotly figure and return fig.to_dict()."""
    if not data:
        raise ValueError("Cannot render chart from empty data records.")

    df = pd.DataFrame(data)

    if req.x not in df.columns:
        raise ValueError(f"Chart x-axis column '{req.x}' not found in data columns: {list(df.columns)}")
    if req.y not in df.columns:
        raise ValueError(f"Chart y-axis column '{req.y}' not found in data columns: {list(df.columns)}")
    if req.color and req.color not in df.columns:
        raise ValueError(f"Chart color column '{req.color}' not found in data columns: {list(df.columns)}")

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

