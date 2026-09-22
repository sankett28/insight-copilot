"""
tools/metrics.py
----------------
Metrics tool — computes aggregated numeric metrics (sums, averages, counts,
rankings, percentiles) from the dataset using DuckDB.

Design contract:
  - All calculations are performed by DuckDB from validated parameters.
  - The LLM never writes SQL and never calculates numbers.
  - Metric inputs are strictly validated against Pydantic MetricsRequest.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent.state import AgentState
from models.schemas import (
    CANONICAL_COLUMNS,
    CATEGORICAL_COLUMNS,
    NUMERIC_COLUMNS,
    MetricsRequest,
    ToolName,
    ToolResult,
)
from utils.data_loader import get_connection

logger = logging.getLogger(__name__)


def metrics_tool_node(state: AgentState) -> dict:
    """LangGraph node: compute aggregated metrics from the dataset.

    Reads:
        state["plan"]         — to extract metric parameters from current step
        state["current_step"] — index of the active plan step

    Writes:
        tool_results — appends a ToolResult (success or error)
    """
    step_idx = state.get("current_step", 0)
    plan = state.get("plan")

    if not plan or step_idx >= len(plan.steps):
        err_msg = f"Metrics tool failed: plan missing or step index {step_idx} out of range."
        return {
            "tool_results": [
                ToolResult(
                    tool=ToolName.METRICS,
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
        req = MetricsRequest.model_validate(raw_params)
        start_t = time.perf_counter()
        data = execute_metrics_request(req)
        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
        existing_results.append(
            ToolResult(
                tool=ToolName.METRICS,
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
        logger.exception("Metrics tool execution error: %s", exc)
        existing_results.append(
            ToolResult(
                tool=ToolName.METRICS,
                step_number=plan_step.step_number,
                success=False,
                data=None,
                error=f"Metrics calculation error: {exc}",
                source_view="dataset",
            )
        )
        return {"tool_results": existing_results}



def execute_metrics_request(req: MetricsRequest) -> list[dict[str, Any]]:
    """Generate safe SQL for a MetricsRequest and execute against DuckDB."""
    conn = get_connection()

    # Determine canonical metric column name
    metric_col = req.metric
    agg_op = req.aggregation.lower()
    if agg_op in ("average", "avg"):
        sql_agg = "AVG"
    elif agg_op == "sum":
        sql_agg = "SUM"
    elif agg_op == "count":
        sql_agg = "COUNT"
    elif agg_op == "min":
        sql_agg = "MIN"
    elif agg_op == "max":
        sql_agg = "MAX"
    elif agg_op == "median":
        sql_agg = "MEDIAN"
    else:
        sql_agg = "SUM"

    # Handle grouping
    group_cols: list[str] = []
    if req.group_by:
        if isinstance(req.group_by, str):
            group_cols = [req.group_by]
        else:
            group_cols = list(req.group_by)

    # Validate group columns against canonical schema
    validated_groups = []
    for g in group_cols:
        matched = False
        for c in CANONICAL_COLUMNS:
            if g.lower() == c.lower():
                validated_groups.append(c)
                matched = True
                break
        if not matched:
            raise ValueError(f"Invalid group_by column '{g}'. Must be one of {CANONICAL_COLUMNS}.")

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
                    # Handle case-insensitive matching for string values if needed
                    where_clauses.append(f"LOWER({matched_col}) = LOWER('{clean_val}')")
                else:
                    where_clauses.append(f"{matched_col} = {val}")

    where_str = " AND ".join(where_clauses)
    metric_alias = f"{agg_op}_{metric_col}".lower()

    if validated_groups:
        group_str = ", ".join(validated_groups)
        sql = (
            f"SELECT {group_str}, {sql_agg}({metric_col}) AS {metric_alias} "
            f"FROM dataset WHERE {where_str} "
            f"GROUP BY {group_str} "
            f"ORDER BY {metric_alias} {req.sort.upper()} "
            f"LIMIT {req.limit or 20}"
        )
    else:
        sql = (
            f"SELECT {sql_agg}({metric_col}) AS {metric_alias} "
            f"FROM dataset WHERE {where_str}"
        )

    logger.info("Executing Metrics SQL: %s", sql)
    df = conn.execute(sql).fetchdf()
    return df.to_dict(orient="records")

