"""
tools/correlation.py
--------------------
Correlation tool — calculates the Pearson correlation coefficient between
two numeric dataset fields in DuckDB, providing mandatory statistical caveats.

Design contract:
  - Deterministic computation using DuckDB CORR(field_a, field_b).
  - Explicitly states: 'Correlation does not imply causation.'
"""

from __future__ import annotations

import logging
from typing import Any

from agent.state import AgentState
from models.schemas import (
    CANONICAL_COLUMNS,
    CorrelationRequest,
    ToolName,
    ToolResult,
)
from utils.data_loader import get_connection

logger = logging.getLogger(__name__)


def correlation_tool_node(state: AgentState) -> dict:
    """LangGraph node: calculate Pearson correlation.

    Reads:
        state["plan"]         — active AnalysisPlan
        state["current_step"] — active step index

    Writes:
        tool_results — appends a ToolResult containing correlation metrics
    """
    step_idx = state.get("current_step", 0)
    plan = state.get("plan")

    if not plan or step_idx >= len(plan.steps):
        err_msg = f"Correlation tool failed: plan missing or step index {step_idx} out of range."
        return {
            "tool_results": [
                ToolResult(
                    tool=ToolName.CORRELATION,
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
        req = CorrelationRequest.model_validate(raw_params)
        data = execute_correlation(req)
        existing_results.append(
            ToolResult(
                tool=ToolName.CORRELATION,
                step_number=plan_step.step_number,
                success=True,
                data=data,
                error=None,
            )
        )
        return {"tool_results": existing_results}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Correlation tool execution error: %s", exc)
        existing_results.append(
            ToolResult(
                tool=ToolName.CORRELATION,
                step_number=plan_step.step_number,
                success=False,
                data=None,
                error=f"Correlation calculation error: {exc}",
            )
        )
        return {"tool_results": existing_results}


def execute_correlation(req: CorrelationRequest) -> dict[str, Any]:
    """Calculate Pearson correlation in DuckDB and return statistical interpretation."""
    conn = get_connection()
    fa = req.field_a
    fb = req.field_b

    # Build WHERE filters safely
    where_clauses: list[str] = [f"{fa} IS NOT NULL", f"{fb} IS NOT NULL"]
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
        f"SELECT "
        f"ROUND(CORR({fa}, {fb}), 4) AS correlation_coefficient, "
        f"COUNT(*) AS sample_size "
        f"FROM dataset "
        f"WHERE {where_str}"
    )

    logger.info("Executing Correlation SQL: %s", sql)
    row = conn.execute(sql).fetchone()

    corr_coef = float(row[0]) if (row and row[0] is not None) else 0.0
    sample_size = int(row[1]) if (row and row[1] is not None) else 0

    # Interpretation
    abs_corr = abs(corr_coef)
    if abs_corr >= 0.8:
        strength = "strong"
    elif abs_corr >= 0.5:
        strength = "moderate"
    elif abs_corr >= 0.2:
        strength = "weak"
    else:
        strength = "negligible"

    direction = "positive" if corr_coef > 0 else "negative" if corr_coef < 0 else "neutral"
    interpretation = f"{strength} {direction} correlation" if abs_corr >= 0.2 else "no significant linear correlation"

    return {
        "field_a": fa,
        "field_b": fb,
        "correlation_coefficient": corr_coef,
        "sample_size": sample_size,
        "interpretation": interpretation,
        "caveat": "Correlation does not imply causation. External factors or common drivers may explain statistical alignment.",
    }
