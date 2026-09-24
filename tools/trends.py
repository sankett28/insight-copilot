"""
tools/trends.py
---------------
Trends tool — analyses a numeric measure over time or across an ordered
dimension using DuckDB.

Design contract:
  - All trend calculations are executed in DuckDB from validated parameters.
  - Results are returned as tabular time-series dictionaries.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent.state import AgentState
from models.schemas import (
    CANONICAL_COLUMNS,
    DATE_COLUMN,
    ToolName,
    ToolResult,
    TrendsRequest,
)
from utils.data_loader import build_sql_where_clause, get_connection

logger = logging.getLogger(__name__)



def trends_tool_node(state: AgentState) -> dict:
    """LangGraph node: perform trend analysis on the dataset.

    Reads:
        state["plan"]         — to extract trend parameters
        state["current_step"] — to identify the correct plan step

    Writes:
        tool_results — appends a ToolResult (success or error)
    """
    step_idx = state.get("current_step", 0)
    plan = state.get("plan")

    if not plan or step_idx >= len(plan.steps):
        err_msg = f"Trends tool failed: plan missing or step index {step_idx} out of range."
        return {
            "tool_results": [
                ToolResult(
                    tool=ToolName.TRENDS,
                    step_number=step_idx + 1,
                    success=False,
                    data=None,
                    error=err_msg,
                )
            ]
        }

    plan_step = plan.steps[step_idx]
    raw_params = plan_step.parameters or {}

    existing_results = list(state.get("tool_results", []))

    # Resolve cross-step sentinel placeholders before Pydantic validation
    from utils.result_resolver import resolve_step_parameters
    raw_params = resolve_step_parameters(raw_params, existing_results)

    try:
        req = TrendsRequest.model_validate(raw_params)
        start_t = time.perf_counter()
        data = execute_trends_request(req)
        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
        existing_results.append(
            ToolResult(
                tool=ToolName.TRENDS,
                step_number=plan_step.step_number,
                success=True,
                data=data,
                error=None,
                source_view="dataset",
                row_count=len(data),
                execution_time_ms=duration_ms,
            )
        )
        return {"tool_results": existing_results}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Trends tool execution error: %s", exc)
        existing_results.append(
            ToolResult(
                tool=ToolName.TRENDS,
                step_number=plan_step.step_number,
                success=False,
                data=None,
                error=f"Trends calculation error: {exc}",
                source_view="dataset",
            )
        )
        return {"tool_results": existing_results}



def execute_trends_request(req: TrendsRequest) -> list[dict[str, Any]]:
    """Generate safe SQL for a TrendsRequest and execute against DuckDB."""
    conn = get_connection()

    metric_col = req.metric
    date_col = req.date_column
    granularity = req.granularity.lower()

    # Build WHERE filters safely
    where_str = build_sql_where_clause(req.filters)
    metric_alias = f"total_{metric_col}".lower()

    # Optional group_by dimension
    group_select = ""
    group_clause = ""
    if req.group_by:
        matched_group = None
        for c in CANONICAL_COLUMNS:
            if req.group_by.lower() == c.lower():
                matched_group = c
                break
        if matched_group:
            group_select = f"{matched_group}, "
            group_clause = f", {matched_group}"

    # DuckDB DATE_TRUNC function
    sql = (
        f"SELECT {group_select}DATE_TRUNC('{granularity}', {date_col})::VARCHAR AS period, "
        f"SUM({metric_col}) AS {metric_alias} "
        f"FROM dataset WHERE {where_str} "
        f"GROUP BY DATE_TRUNC('{granularity}', {date_col}){group_clause} "
        f"ORDER BY period ASC"
    )

    print(f"[Tool: trends] Executing SQL: {sql}")
    logger.info("Executing Trends SQL: %s", sql)
    df = conn.execute(sql).fetchdf()


    # Clean date formatting for period
    records = df.to_dict(orient="records")
    for r in records:
        if "period" in r and isinstance(r["period"], str):
            # Trim timestamp to YYYY-MM-DD or YYYY-MM if appropriate
            r["period"] = r["period"].split(" ")[0]

    return records

