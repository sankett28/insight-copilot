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
from typing import Any

from agent.state import AgentState
from models.schemas import (
    CANONICAL_COLUMNS,
    SegmentationRequest,
    ToolName,
    ToolResult,
)
from utils.data_loader import get_connection

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
        data = execute_segmentation(req)
        existing_results.append(
            ToolResult(
                tool=ToolName.SEGMENTATION,
                step_number=plan_step.step_number,
                success=True,
                data=data,
                error=None,
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

    # Build WHERE filters safely
    where_clauses: list[str] = [f"{dim_p} IS NOT NULL", f"{dim_s} IS NOT NULL", f"{metric_col} IS NOT NULL"]
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

    sql = (
        f"SELECT {dim_p}, {dim_s}, "
        f"ROUND({sql_agg}({metric_col}), 2) AS {val_alias} "
        f"FROM dataset "
        f"WHERE {where_str} "
        f"GROUP BY {dim_p}, {dim_s} "
        f"ORDER BY {val_alias} DESC "
        f"LIMIT {req.limit}"
    )

    logger.info("Executing Segmentation SQL: %s", sql)
    df = conn.execute(sql).fetchdf()
    return df.to_dict(orient="records")
