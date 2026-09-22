"""
tools/variance.py
-----------------
Variance tool — evaluates period-over-period change (day, week, month, quarter, year)
calculating previous period metrics, absolute deltas, and percentage growth via DuckDB.

Design contract:
  - Uses DuckDB CTE and LAG window functions.
  - First period returns None for deltas.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import pandas as pd

from agent.state import AgentState
from models.schemas import (
    CANONICAL_COLUMNS,
    DATE_COLUMN,
    ToolName,
    ToolResult,
    VarianceRequest,
)
from utils.data_loader import get_connection

logger = logging.getLogger(__name__)


def variance_tool_node(state: AgentState) -> dict:
    """LangGraph node: compute period-over-period variance.

    Reads:
        state["plan"]         — active AnalysisPlan
        state["current_step"] — active step index

    Writes:
        tool_results — appends a ToolResult containing variance records
    """
    step_idx = state.get("current_step", 0)
    plan = state.get("plan")

    if not plan or step_idx >= len(plan.steps):
        err_msg = f"Variance tool failed: plan missing or step index {step_idx} out of range."
        return {
            "tool_results": [
                ToolResult(
                    tool=ToolName.VARIANCE,
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
        req = VarianceRequest.model_validate(raw_params)
        start_t = time.perf_counter()
        data = execute_variance(req)
        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
        existing_results.append(
            ToolResult(
                tool=ToolName.VARIANCE,
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
        logger.exception("Variance tool execution error: %s", exc)
        existing_results.append(
            ToolResult(
                tool=ToolName.VARIANCE,
                step_number=plan_step.step_number,
                success=False,
                data=None,
                error=f"Variance calculation error: {exc}",
                source_view="dataset",
            )
        )
        return {"tool_results": existing_results}


def execute_variance(req: VarianceRequest) -> list[dict[str, Any]]:
    """Generate safe SQL for period-over-period variance with CTE and LAG."""
    conn = get_connection()

    metric_col = req.metric
    granularity = req.granularity.lower()

    # Build WHERE filters safely
    where_clauses: list[str] = ["1=1"]
    if req.filters:
        for col, val in req.filters.items():
            matched_col = None
            for c in CANONICAL_COLUMNS:
                if col.lower() == c.lower():
                    matched_col = c
                    break
            if matched_col:
                if isinstance(val, str):
                    clean_val = val.replace("'", "''")
                    where_clauses.append(f"LOWER({matched_col}) = LOWER('{clean_val}')")
                else:
                    where_clauses.append(f"{matched_col} = {val}")

    where_str = " AND ".join(where_clauses)
    metric_alias = f"total_{metric_col}".lower()

    # Optional group_by
    group_select = ""
    group_clause = ""
    partition_clause = ""
    if req.group_by:
        matched_group = None
        for c in CANONICAL_COLUMNS:
            if req.group_by.lower() == c.lower():
                matched_group = c
                break
        if matched_group:
            group_select = f"{matched_group}, "
            group_clause = f", {matched_group}"
            partition_clause = f"PARTITION BY {matched_group} "

    sql = (
        f"WITH series AS ("
        f"  SELECT {group_select}DATE_TRUNC('{granularity}', {DATE_COLUMN})::VARCHAR AS period, "
        f"         SUM({metric_col}) AS {metric_alias} "
        f"  FROM dataset "
        f"  WHERE {where_str} "
        f"  GROUP BY DATE_TRUNC('{granularity}', {DATE_COLUMN}){group_clause} "
        f") "
        f"SELECT {group_select}period, "
        f"       ROUND({metric_alias}, 2) AS {metric_alias}, "
        f"       ROUND(LAG({metric_alias}) OVER ({partition_clause}ORDER BY period), 2) AS prev_{metric_alias}, "
        f"       ROUND({metric_alias} - LAG({metric_alias}) OVER ({partition_clause}ORDER BY period), 2) AS absolute_change, "
        f"       ROUND(({metric_alias} - LAG({metric_alias}) OVER ({partition_clause}ORDER BY period)) * 100.0 / NULLIF(LAG({metric_alias}) OVER ({partition_clause}ORDER BY period), 0), 2) AS pct_change "
        f"FROM series "
        f"ORDER BY period ASC{group_clause}"
    )

    logger.info("Executing Variance SQL: %s", sql)
    df = conn.execute(sql).fetchdf()
    # Convert numpy/pandas NaN to None for clean JSON serialization
    df = df.astype(object).where(pd.notnull(df), None)
    records = df.to_dict(orient="records")
    for r in records:
        if "period" in r and isinstance(r["period"], str):
            r["period"] = r["period"].split(" ")[0]
    return records
