"""
tools/profitability.py
----------------------
Profitability tool — evaluates financial performance across groups, calculating
Revenue, Cost, Profit, and derived profit margin (Profit / Revenue * 100).

Design contract:
  - Explicitly computes profit margin in SQL: SUM(Profit) / NULLIF(SUM(Revenue), 0) * 100
  - Prevents conflation of top revenue with top margin.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent.state import AgentState
from models.schemas import (
    CANONICAL_COLUMNS,
    ProfitabilityRequest,
    ToolName,
    ToolResult,
)
from utils.data_loader import build_sql_where_clause, get_connection

logger = logging.getLogger(__name__)


def profitability_tool_node(state: AgentState) -> dict:
    """LangGraph node: compute profitability metrics.

    Reads:
        state["plan"]         — active AnalysisPlan
        state["current_step"] — active step index

    Writes:
        tool_results — appends a ToolResult containing profitability records
    """
    step_idx = state.get("current_step", 0)
    plan = state.get("plan")

    if not plan or step_idx >= len(plan.steps):
        err_msg = f"Profitability tool failed: plan missing or step index {step_idx} out of range."
        return {
            "tool_results": [
                ToolResult(
                    tool=ToolName.PROFITABILITY,
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
        req = ProfitabilityRequest.model_validate(raw_params)
        start_t = time.perf_counter()
        data = execute_profitability(req)
        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
        existing_results.append(
            ToolResult(
                tool=ToolName.PROFITABILITY,
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
        logger.exception("Profitability tool execution error: %s", exc)
        existing_results.append(
            ToolResult(
                tool=ToolName.PROFITABILITY,
                step_number=plan_step.step_number,
                success=False,
                data=None,
                error=f"Profitability calculation error: {exc}",
                source_view="dataset",
            )
        )
        return {"tool_results": existing_results}


def execute_profitability(req: ProfitabilityRequest) -> list[dict[str, Any]]:
    """Generate safe SQL for profitability analysis and execute against DuckDB."""
    conn = get_connection()
    dim_col = req.dimension

    where_str = build_sql_where_clause(req.filters)
    sort_col = req.sort_by if req.sort_by == "profit_margin_pct" else f"sum_{req.sort_by}".lower()

    sql = (
        f"SELECT {dim_col}, "
        f"ROUND(SUM(Revenue), 2) AS sum_revenue, "
        f"ROUND(SUM(Cost), 2) AS sum_cost, "
        f"ROUND(SUM(Profit), 2) AS sum_profit, "
        f"ROUND(SUM(Profit) * 100.0 / NULLIF(SUM(Revenue), 0), 2) AS profit_margin_pct "
        f"FROM dataset "
        f"WHERE {where_str} AND {dim_col} IS NOT NULL "
        f"GROUP BY {dim_col} "
        f"ORDER BY {sort_col} DESC "
        f"LIMIT {req.limit}"
    )

    print(f"[Tool: profitability] Executing SQL: {sql}")
    logger.info("Executing Profitability SQL: %s", sql)
    df = conn.execute(sql).fetchdf()
    return df.to_dict(orient="records")

