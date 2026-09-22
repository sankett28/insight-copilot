"""
tools/contribution.py
--------------------
Contribution tool — calculates the absolute and percentage contribution of each
dimension value to a grand total using DuckDB window functions.

Design contract:
  - Percentage share computed in SQL: SUM(metric) * 100.0 / SUM(SUM(metric)) OVER ()
  - Sum of percentages across full categorical dimensions equals 100.0%.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent.state import AgentState
from models.schemas import (
    CANONICAL_COLUMNS,
    ContributionRequest,
    ToolName,
    ToolResult,
)
from utils.data_loader import get_connection

logger = logging.getLogger(__name__)


def contribution_tool_node(state: AgentState) -> dict:
    """LangGraph node: compute contribution breakdown.

    Reads:
        state["plan"]         — active AnalysisPlan
        state["current_step"] — active step index

    Writes:
        tool_results — appends a ToolResult containing contribution records
    """
    step_idx = state.get("current_step", 0)
    plan = state.get("plan")

    if not plan or step_idx >= len(plan.steps):
        err_msg = f"Contribution tool failed: plan missing or step index {step_idx} out of range."
        return {
            "tool_results": [
                ToolResult(
                    tool=ToolName.CONTRIBUTION,
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
        req = ContributionRequest.model_validate(raw_params)
        start_t = time.perf_counter()
        data = execute_contribution(req)
        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
        existing_results.append(
            ToolResult(
                tool=ToolName.CONTRIBUTION,
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
        logger.exception("Contribution tool execution error: %s", exc)
        existing_results.append(
            ToolResult(
                tool=ToolName.CONTRIBUTION,
                step_number=plan_step.step_number,
                success=False,
                data=None,
                error=f"Contribution calculation error: {exc}",
                source_view="dataset",
            )
        )
        return {"tool_results": existing_results}


def execute_contribution(req: ContributionRequest) -> list[dict[str, Any]]:
    """Generate safe SQL with window functions and execute against DuckDB."""
    conn = get_connection()

    metric_col = req.metric
    dim_col = req.dimension
    agg_op = req.aggregation.lower()
    sql_agg = "COUNT" if agg_op == "count" else "AVG" if agg_op == "avg" else "SUM"

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
    metric_alias = f"{agg_op}_{metric_col}".lower()
    limit_clause = f" LIMIT {req.limit}" if req.limit else ""

    sql = (
        f"SELECT {dim_col}, "
        f"ROUND({sql_agg}({metric_col}), 2) AS {metric_alias}, "
        f"ROUND({sql_agg}({metric_col}) * 100.0 / NULLIF(SUM({sql_agg}({metric_col})) OVER (), 0), 2) AS pct_of_total "
        f"FROM dataset "
        f"WHERE {where_str} AND {dim_col} IS NOT NULL "
        f"GROUP BY {dim_col} "
        f"ORDER BY {metric_alias} DESC"
        f"{limit_clause}"
    )

    logger.info("Executing Contribution SQL: %s", sql)
    df = conn.execute(sql).fetchdf()
    return df.to_dict(orient="records")
