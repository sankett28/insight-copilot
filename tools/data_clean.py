"""
tools/data_clean.py
-------------------
Data cleaning tool node for interactive dataset hygiene and typo resolution.

Design contract:
  - Takes a DataCleanRequest with target columns and cleaning operations.
  - Interactively updates the active 'dataset' view in DuckDB via utils/data_cleaner.py.
  - Returns a detailed Before -> After audit transformation dictionary in ToolResult.
"""

from __future__ import annotations

import logging
from typing import Any

from agent.state import AgentState
from models.schemas import DataCleanRequest, ToolName, ToolResult
from utils.data_cleaner import apply_cleaning_to_duckdb
from utils.data_loader import get_connection

logger = logging.getLogger(__name__)


def data_clean_tool_node(state: AgentState) -> dict:
    """LangGraph node: execute interactive data cleaning operations.

    Reads:
        state["plan"]         — active AnalysisPlan
        state["current_step"] — active step index

    Writes:
        tool_results — appends a ToolResult containing the cleaning audit summary
    """
    step_idx = state.get("current_step", 0)
    plan = state.get("plan")

    if not plan or step_idx >= len(plan.steps):
        err_msg = f"DataClean tool failed: plan missing or step index {step_idx} out of range."
        return {
            "tool_results": [
                ToolResult(
                    tool=ToolName.DATA_CLEAN,
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
        clean_req = DataCleanRequest.model_validate(raw_params)
        audit_summary = execute_data_clean(clean_req)

        existing_results.append(
            ToolResult(
                tool=ToolName.DATA_CLEAN,
                step_number=plan_step.step_number,
                success=True,
                data=audit_summary,
            )
        )
        return {"tool_results": existing_results}

    except Exception as exc:  # noqa: BLE001
        logger.exception("DataClean tool execution failed: %s", exc)
        existing_results.append(
            ToolResult(
                tool=ToolName.DATA_CLEAN,
                step_number=plan_step.step_number,
                success=False,
                data=None,
                error=f"DataClean error: {exc}",
            )
        )
        return {"tool_results": existing_results}


def execute_data_clean(req: DataCleanRequest) -> dict[str, Any]:
    """Execute data cleaning transformations on DuckDB and return audit metrics."""
    conn = get_connection()
    return apply_cleaning_to_duckdb(conn, req)
