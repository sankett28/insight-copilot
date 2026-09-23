"""
tools/data_query.py
-------------------
Data Query tool — retrieves raw or filtered rows from the dataset using DuckDB.

Design contract:
  - All SQL is generated deterministically from structured DataQueryRequest parameters.
  - LLM never writes SQL.
  - DuckDB runs in-process.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent.state import AgentState
from models.schemas import (
    CANONICAL_COLUMNS,
    DataQueryRequest,
    ToolName,
    ToolResult,
)
from utils.data_loader import build_sql_where_clause, get_connection

logger = logging.getLogger(__name__)



def data_query_tool_node(state: AgentState) -> dict:
    """LangGraph node: execute a data query against the loaded dataset.

    Reads:
        state["plan"]         — to extract query parameters
        state["current_step"] — to identify the active plan step

    Writes:
        tool_results — appends a ToolResult (success or error)
    """
    step_idx = state.get("current_step", 0)
    plan = state.get("plan")

    if not plan or step_idx >= len(plan.steps):
        err_msg = f"DataQuery tool failed: plan missing or step index {step_idx} out of range."
        return {
            "tool_results": [
                ToolResult(
                    tool=ToolName.DATA_QUERY,
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

    try:
        req = DataQueryRequest.model_validate(raw_params)
        start_t = time.perf_counter()
        data = execute_data_query_request(req)
        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
        existing_results.append(
            ToolResult(
                tool=ToolName.DATA_QUERY,
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
        logger.exception("DataQuery tool execution error: %s", exc)
        existing_results.append(
            ToolResult(
                tool=ToolName.DATA_QUERY,
                step_number=plan_step.step_number,
                success=False,
                data=None,
                error=f"DataQuery calculation error: {exc}",
                source_view="dataset",
            )
        )
        return {"tool_results": existing_results}



def execute_data_query_request(req: DataQueryRequest) -> list[dict[str, Any]]:
    """Generate safe SQL for a DataQueryRequest and execute against DuckDB."""
    conn = get_connection()

    # Column selection
    if req.columns:
        selected_cols = []
        for requested in req.columns:
            for canonical in CANONICAL_COLUMNS:
                if requested.lower() == canonical.lower():
                    selected_cols.append(canonical)
                    break
        if not selected_cols:
            selected_cols = CANONICAL_COLUMNS
        cols_str = ", ".join(selected_cols)
    else:
        cols_str = "*"

    # Build WHERE filters safely
    where_str = build_sql_where_clause(req.filters)

    # Sorting
    order_clause = ""
    if req.sort_by:
        matched_sort = None
        for c in CANONICAL_COLUMNS:
            if req.sort_by.lower() == c.lower():
                matched_sort = c
                break
        if matched_sort:
            order_clause = f" ORDER BY {matched_sort} {req.sort_order.upper()}"

    limit = min(req.limit, 100)

    sql = f"SELECT {cols_str} FROM dataset WHERE {where_str}{order_clause} LIMIT {limit}"

    print(f"[Tool: data_query] Executing SQL: {sql}")
    logger.info("Executing DataQuery SQL: %s", sql)
    df = conn.execute(sql).fetchdf()


    # Format datetime objects as ISO strings
    records = df.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                r[k] = v.isoformat()

    return records

