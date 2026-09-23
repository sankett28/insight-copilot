"""
tools/segmentation.py
--------------------
Segmentation tool — performs multi-dimensional cross-tabulation across two distinct
categorical dimensions (e.g., Region × Category) aggregated in DuckDB.

Design contract:
  - Multi-column GROUP BY with aggregation.
  - Returns structured 2D combination records.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent.state import AgentState
from models.schemas import (
    CANONICAL_COLUMNS,
    SegmentationRequest,
    ToolName,
    ToolResult,
)
from utils.data_loader import build_sql_where_clause, get_connection

logger = logging.getLogger(__name__)


def segmentation_tool_node(state: AgentState) -> dict:
    """LangGraph node: execute 2D cross-segmentation analysis.

    Reads:
        state["plan"]         — active AnalysisPlan
        state["current_step"] — active step index

    Writes:
        tool_results — appends a ToolResult containing segmentation records
    """
    step_idx = state.get("current_step", 0)
    plan = state.get("plan")

    if not plan or step_idx >= len(plan.steps):
        err_msg = f"Segmentation tool failed: plan missing or step index {step_idx} out of range."
        return {
            "tool_results": [
                ToolResult(
                    tool=ToolName.SEGMENTATION,
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
        req = SegmentationRequest.model_validate(raw_params)
        start_t = time.perf_counter()
        data = execute_segmentation(req)
        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
        existing_results.append(
            ToolResult(
                tool=ToolName.SEGMENTATION,
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
        logger.exception("Segmentation tool execution error: %s", exc)
        existing_results.append(
            ToolResult(
                tool=ToolName.SEGMENTATION,
                step_number=plan_step.step_number,
                success=False,
                data=None,
                error=f"Segmentation calculation error: {exc}",
                source_view="dataset",
            )
        )
        return {"tool_results": existing_results}


def execute_segmentation(req: SegmentationRequest) -> list[dict[str, Any]]:
    """Execute multi-dimensional cross-tabulation in DuckDB."""
    conn = get_connection()
    metric_col = req.metric
    dim_p = req.dimension_primary
    dim_s = req.dimension_secondary
    agg_op = req.aggregation.lower()

    sql_agg = "COUNT" if agg_op == "count" else "AVG" if agg_op in ("avg", "average") else "MIN" if agg_op == "min" else "MAX" if agg_op == "max" else "SUM"
    val_alias = f"{agg_op}_{metric_col}".lower()

    where_filter = build_sql_where_clause(req.filters)
    where_str = f"{dim_p} IS NOT NULL AND {dim_s} IS NOT NULL AND {metric_col} IS NOT NULL AND {where_filter}"

    sql = (
        f"SELECT {dim_p}, {dim_s}, "
        f"ROUND({sql_agg}({metric_col}), 2) AS {val_alias} "
        f"FROM dataset "
        f"WHERE {where_str} "
        f"GROUP BY {dim_p}, {dim_s} "
        f"ORDER BY {val_alias} DESC "
        f"LIMIT {req.limit}"
    )

    print(f"[Tool: segmentation] Executing SQL: {sql}")
    logger.info("Executing Segmentation SQL: %s", sql)
    df = conn.execute(sql).fetchdf()
    return df.to_dict(orient="records")

