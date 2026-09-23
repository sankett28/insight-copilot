"""
tools/anomaly_detection.py
--------------------------
Anomaly detection tool — identifies statistical outliers in numeric metrics
using IQR (Interquartile Range) or Z-score methods natively via DuckDB.

Design contract:
  - Deterministic statistical calculation in DuckDB (PERCENTILE_CONT or AVG/STDDEV).
  - Returns detected anomaly records along with boundary metrics.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent.state import AgentState
from models.schemas import (
    CANONICAL_COLUMNS,
    AnomalyRequest,
    ToolName,
    ToolResult,
)
from utils.data_loader import build_sql_where_clause, get_connection

logger = logging.getLogger(__name__)


def anomaly_detection_tool_node(state: AgentState) -> dict:
    """LangGraph node: execute statistical anomaly detection.

    Reads:
        state["plan"]         — active AnalysisPlan
        state["current_step"] — active step index

    Writes:
        tool_results — appends a ToolResult containing anomaly findings
    """
    step_idx = state.get("current_step", 0)
    plan = state.get("plan")

    if not plan or step_idx >= len(plan.steps):
        err_msg = f"AnomalyDetection tool failed: plan missing or step index {step_idx} out of range."
        return {
            "tool_results": [
                ToolResult(
                    tool=ToolName.ANOMALY_DETECTION,
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
        req = AnomalyRequest.model_validate(raw_params)
        start_t = time.perf_counter()
        data = execute_anomaly_detection(req)
        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
        existing_results.append(
            ToolResult(
                tool=ToolName.ANOMALY_DETECTION,
                step_number=plan_step.step_number,
                success=True,
                data=data,
                error=None,
                source_view="dataset",
                row_count=data.get("total_anomalies") if isinstance(data, dict) else len(data) if isinstance(data, list) else 1,
                execution_time_ms=duration_ms,
            )
        )
        return {"tool_results": existing_results}
    except Exception as exc:  # noqa: BLE001
        logger.exception("AnomalyDetection tool execution error: %s", exc)
        existing_results.append(
            ToolResult(
                tool=ToolName.ANOMALY_DETECTION,
                step_number=plan_step.step_number,
                success=False,
                data=None,
                error=f"AnomalyDetection calculation error: {exc}",
                source_view="dataset",
            )
        )
        return {"tool_results": existing_results}


def execute_anomaly_detection(req: AnomalyRequest) -> dict[str, Any]:
    """Generate safe SQL for outlier detection and execute against DuckDB."""
    conn = get_connection()
    metric_col = req.metric
    method = req.method.lower()
    threshold = float(req.threshold)

    where_filter = build_sql_where_clause(req.filters)
    where_str = f"{metric_col} IS NOT NULL AND {where_filter}"

    if method == "zscore":
        sql_stats = (
            f"SELECT AVG({metric_col}) AS mean_val, STDDEV({metric_col}) AS std_val "
            f"FROM dataset WHERE {where_str}"
        )
        print(f"[Tool: anomaly_detection] Executing Stats SQL: {sql_stats}")
        stats_row = conn.execute(sql_stats).fetchone()
        mean_val = float(stats_row[0]) if (stats_row and stats_row[0] is not None) else 0.0
        std_val = float(stats_row[1]) if (stats_row and stats_row[1] is not None) else 1.0

        upper_bound = round(mean_val + threshold * std_val, 2)
        lower_bound = round(mean_val - threshold * std_val, 2)

        sql_anomalies = (
            f"SELECT Date::VARCHAR AS Date, Region, Product, Salesperson, Category, "
            f"ROUND({metric_col}, 2) AS {metric_col}, "
            f"ROUND(({metric_col} - {mean_val}) / NULLIF({std_val}, 0), 2) AS z_score, "
            f"CASE WHEN {metric_col} > {upper_bound} THEN 'high' ELSE 'low' END AS anomaly_type "
            f"FROM dataset "
            f"WHERE {where_str} AND ({metric_col} > {upper_bound} OR {metric_col} < {lower_bound}) "
            f"ORDER BY ABS({metric_col} - {mean_val}) DESC "
            f"LIMIT 50"
        )
        print(f"[Tool: anomaly_detection] Executing Outliers SQL: {sql_anomalies}")
        df = conn.execute(sql_anomalies).fetchdf()
        rows = df.to_dict(orient="records")
        for r in rows:
            if "Date" in r and isinstance(r["Date"], str):
                r["Date"] = r["Date"].split(" ")[0]

        return {
            "metric": metric_col,
            "method": "zscore",
            "threshold": threshold,
            "mean": round(mean_val, 2),
            "stddev": round(std_val, 2),
            "upper_bound": upper_bound,
            "lower_bound": lower_bound,
            "anomalies_found": len(rows),
            "rows": rows,
        }

    # Default: IQR Method
    sql_iqr = (
        f"SELECT "
        f"PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {metric_col}) AS q1, "
        f"PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {metric_col}) AS q3 "
        f"FROM dataset WHERE {where_str}"
    )
    print(f"[Tool: anomaly_detection] Executing IQR SQL: {sql_iqr}")
    iqr_row = conn.execute(sql_iqr).fetchone()
    q1 = float(iqr_row[0]) if (iqr_row and iqr_row[0] is not None) else 0.0
    q3 = float(iqr_row[1]) if (iqr_row and iqr_row[1] is not None) else 0.0
    iqr = q3 - q1

    upper_bound = round(q3 + threshold * iqr, 2)
    lower_bound = round(q1 - threshold * iqr, 2)

    sql_anomalies = (
        f"SELECT Date::VARCHAR AS Date, Region, Product, Salesperson, Category, "
        f"ROUND({metric_col}, 2) AS {metric_col}, "
        f"CASE WHEN {metric_col} > {upper_bound} THEN 'high' ELSE 'low' END AS anomaly_type "
        f"FROM dataset "
        f"WHERE {where_str} AND ({metric_col} > {upper_bound} OR {metric_col} < {lower_bound}) "
        f"ORDER BY {metric_col} DESC "
        f"LIMIT 50"
    )
    print(f"[Tool: anomaly_detection] Executing Outliers SQL: {sql_anomalies}")
    df = conn.execute(sql_anomalies).fetchdf()
    rows = df.to_dict(orient="records")
    for r in rows:
        if "Date" in r and isinstance(r["Date"], str):
            r["Date"] = r["Date"].split(" ")[0]

    return {
        "metric": metric_col,
        "method": "iqr",
        "threshold": threshold,
        "q1": round(q1, 2),
        "q3": round(q3, 2),
        "iqr": round(iqr, 2),
        "upper_bound": upper_bound,
        "lower_bound": lower_bound,
        "anomalies_found": len(rows),
        "rows": rows,
    }

