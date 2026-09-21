"""
tools/compare.py
----------------
Compare tool — compares numeric metrics across two distinct entities, categories,
or groups with absolute and percentage delta calculations via DuckDB.

Design contract:
  - All calculations executed in DuckDB from validated parameters.
  - Returns side-by-side entity values, absolute delta, and percentage delta.
"""

from __future__ import annotations

import logging
from typing import Any

from agent.state import AgentState
from models.schemas import (
    CANONICAL_COLUMNS,
    CompareRequest,
    ToolName,
    ToolResult,
)
from utils.data_loader import get_connection

logger = logging.getLogger(__name__)


def compare_tool_node(state: AgentState) -> dict:
    """LangGraph node: execute comparison between two entities.

    Reads:
        state["plan"]         — active AnalysisPlan
        state["current_step"] — active step index

    Writes:
        tool_results — appends a ToolResult containing the comparison dictionary
    """
    step_idx = state.get("current_step", 0)
    plan = state.get("plan")

    if not plan or step_idx >= len(plan.steps):
        err_msg = f"Compare tool failed: plan missing or step index {step_idx} out of range."
        return {
            "tool_results": [
                ToolResult(
                    tool=ToolName.COMPARE,
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
        req = CompareRequest.model_validate(raw_params)
        data = execute_compare(req)
        existing_results.append(
            ToolResult(
                tool=ToolName.COMPARE,
                step_number=plan_step.step_number,
                success=True,
                data=data,
                error=None,
            )
        )
        return {"tool_results": existing_results}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Compare tool execution error: %s", exc)
        existing_results.append(
            ToolResult(
                tool=ToolName.COMPARE,
                step_number=plan_step.step_number,
                success=False,
                data=None,
                error=f"Compare calculation error: {exc}",
            )
        )
        return {"tool_results": existing_results}


def execute_compare(req: CompareRequest) -> dict[str, Any]:
    """Generate safe SQL for CompareRequest and execute against DuckDB."""
    conn = get_connection()

    metric_col = req.metric
    dim_col = req.dimension
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
    else:
        sql_agg = "SUM"

    # Base WHERE filters
    base_where: list[str] = ["1=1"]
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
                    base_where.append(f"LOWER({matched_col}) = LOWER('{clean_val}')")
                else:
                    base_where.append(f"{matched_col} = {val}")

    base_where_str = " AND ".join(base_where)

    # Clean entity values for SQL
    clean_val_a = req.value_a.replace("'", "''")
    clean_val_b = req.value_b.replace("'", "''")

    sql_a = (
        f"SELECT {sql_agg}({metric_col}) AS val FROM dataset "
        f"WHERE {base_where_str} AND LOWER({dim_col}) = LOWER('{clean_val_a}')"
    )
    sql_b = (
        f"SELECT {sql_agg}({metric_col}) AS val FROM dataset "
        f"WHERE {base_where_str} AND LOWER({dim_col}) = LOWER('{clean_val_b}')"
    )

    logger.info("Executing Compare SQL A: %s", sql_a)
    res_a = conn.execute(sql_a).fetchone()
    logger.info("Executing Compare SQL B: %s", sql_b)
    res_b = conn.execute(sql_b).fetchone()

    val_a = round(float(res_a[0]), 2) if (res_a and res_a[0] is not None) else 0.0
    val_b = round(float(res_b[0]), 2) if (res_b and res_b[0] is not None) else 0.0

    abs_delta = round(val_a - val_b, 2)
    if val_b != 0:
        pct_delta = round((abs_delta / val_b) * 100.0, 2)
    else:
        pct_delta = None

    return {
        "metric": metric_col,
        "aggregation": req.aggregation,
        "dimension": dim_col,
        "entity_a": {"label": req.value_a, "value": val_a},
        "entity_b": {"label": req.value_b, "value": val_b},
        "absolute_delta": abs_delta,
        "pct_delta": pct_delta,
    }
