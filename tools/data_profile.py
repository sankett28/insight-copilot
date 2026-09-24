"""
tools/data_profile.py
---------------------
Data Profile tool — computes comprehensive dataset overview, structural metrics,
statistical distributions, and surfaces data quality warnings via DuckDB.

Design contract:
  - Profiles the registered DuckDB view 'dataset' deterministically.
  - Returns a single structured dictionary in ToolResult.data.
  - Data quality findings are surfaced honestly as observable warnings, never mutated.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent.state import AgentState
from models.schemas import (
    CANONICAL_COLUMNS,
    CATEGORICAL_COLUMNS,
    DATE_COLUMN,
    NUMERIC_COLUMNS,
    DataProfileRequest,
    ToolName,
    ToolResult,
)
from utils.data_loader import get_connection

logger = logging.getLogger(__name__)


def data_profile_tool_node(state: AgentState) -> dict:
    """LangGraph node: execute dataset profiling.

    Reads:
        state["plan"]         — active AnalysisPlan
        state["current_step"] — active step index

    Writes:
        tool_results — appends a ToolResult containing the dataset profile dictionary
    """
    step_idx = state.get("current_step", 0)
    plan = state.get("plan")

    if not plan or step_idx >= len(plan.steps):
        err_msg = f"DataProfile tool failed: plan missing or step index {step_idx} out of range."
        return {
            "tool_results": [
                ToolResult(
                    tool=ToolName.DATA_PROFILE,
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
        req = DataProfileRequest.model_validate(raw_params)
        start_t = time.perf_counter()
        profile_data = execute_data_profile(req)
        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
        existing_results.append(
            ToolResult(
                tool=ToolName.DATA_PROFILE,
                step_number=plan_step.step_number,
                success=True,
                data=profile_data,
                error=None,
                source_view="dataset",
                row_count=profile_data.get("row_count") if isinstance(profile_data, dict) else 1,
                execution_time_ms=duration_ms,
            )
        )
        return {"tool_results": existing_results}
    except Exception as exc:  # noqa: BLE001
        logger.exception("DataProfile tool execution error: %s", exc)
        existing_results.append(
            ToolResult(
                tool=ToolName.DATA_PROFILE,
                step_number=plan_step.step_number,
                success=False,
                data=None,
                error=f"DataProfile calculation error: {exc}",
                source_view="dataset",
            )
        )
        return {"tool_results": existing_results}


def execute_data_profile(req: DataProfileRequest | None = None) -> dict[str, Any]:
    """Perform dataset structural profiling and quality checks against DuckDB."""
    conn = get_connection()

    # 1. Basic row and column metrics
    row_count = conn.execute("SELECT COUNT(*) FROM dataset").fetchone()[0]
    describe_rows = conn.execute("DESCRIBE dataset").fetchall()
    column_count = len(describe_rows)

    # 2. Date range
    date_min, date_max = conn.execute(
        f"SELECT MIN({DATE_COLUMN})::VARCHAR, MAX({DATE_COLUMN})::VARCHAR FROM dataset"
    ).fetchone()
    date_range = {
        "min": str(date_min).split(" ")[0] if date_min else None,
        "max": str(date_max).split(" ")[0] if date_max else None,
    }

    # 3. Numeric column summary stats (min, max, mean, stddev)
    numeric_summary: dict[str, dict[str, float | None]] = {}
    for col in NUMERIC_COLUMNS:
        res = conn.execute(
            f"SELECT MIN({col}), MAX({col}), AVG({col}), STDDEV({col}) FROM dataset"
        ).fetchone()
        numeric_summary[col] = {
            "min": round(float(res[0]), 2) if res[0] is not None else None,
            "max": round(float(res[1]), 2) if res[1] is not None else None,
            "mean": round(float(res[2]), 2) if res[2] is not None else None,
            "stddev": round(float(res[3]), 2) if res[3] is not None else None,
        }

    # 4. Categorical cardinality
    categorical_cardinality: dict[str, int] = {}
    for col in CATEGORICAL_COLUMNS:
        card = conn.execute(f"SELECT COUNT(DISTINCT {col}) FROM dataset").fetchone()[0]
        categorical_cardinality[col] = int(card)

    # 5. Null counts across all canonical columns
    null_counts: dict[str, int] = {}
    for col in CANONICAL_COLUMNS:
        nc = conn.execute(f"SELECT COUNT(*) FROM dataset WHERE {col} IS NULL").fetchone()[0]
        null_counts[col] = int(nc)

    # 6. Data quality warnings
    warnings: list[str] = []

    # Check for negative profit
    neg_profit_count = conn.execute("SELECT COUNT(*) FROM dataset WHERE Profit < 0").fetchone()[0]
    if neg_profit_count > 0:
        warnings.append(f"{neg_profit_count} rows contain negative Profit")

    # Check for zero or negative revenue
    neg_rev_count = conn.execute("SELECT COUNT(*) FROM dataset WHERE Revenue <= 0").fetchone()[0]
    if neg_rev_count > 0:
        warnings.append(f"{neg_rev_count} rows contain zero or negative Revenue")

    # Check for duplicate rows across primary keys / attributes
    unique_rows = conn.execute(
        f"SELECT COUNT(*) FROM (SELECT DISTINCT {', '.join(CANONICAL_COLUMNS)} FROM dataset)"
    ).fetchone()[0]
    dup_count = row_count - unique_rows
    if dup_count > 0:
        warnings.append(f"{dup_count} duplicate rows detected")

    # Check for any column nulls in warnings
    total_nulls = sum(null_counts.values())
    if total_nulls > 0:
        warnings.append(f"{total_nulls} total null values found across dataset columns")

    return {
        "dataset_name": "Sales_Dataset_2024",
        "row_count": row_count,
        "column_count": column_count,
        "date_range": date_range,
        "numeric_summary": numeric_summary,
        "categorical_cardinality": categorical_cardinality,
        "null_counts": null_counts,
        "data_quality_warnings": warnings,
    }
