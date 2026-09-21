"""
tools/data_query.py
-------------------
Data Query tool — retrieves raw or filtered rows from the dataset using DuckDB.

Design contract:
  - All SQL is generated deterministically from structured parameters.
  - The LLM never writes SQL and never sees raw query results before the
    synthesizer receives them.
  - DuckDB runs in-process; no network calls.

Current status: PLACEHOLDER — returns a stub result.
Full implementation will be added in the next development phase once the
dataset and data_loader utility are established.
"""

from __future__ import annotations

import logging

from agent.state import AgentState
from models.schemas import ToolName, ToolResult

logger = logging.getLogger(__name__)


def data_query_tool_node(state: AgentState) -> dict:
    """LangGraph node: execute a data query against the loaded dataset.

    Reads:
        state["plan"]         — to extract query parameters
        state["current_step"] — to identify the correct plan step

    Writes:
        tool_results — appends a ToolResult (success or error)
    """
    step = state.get("current_step", 0)
    plan = state.get("plan")

    logger.info("data_query_tool_node: executing step %d", step)

    # TODO: Extract query parameters from plan.steps[step] and run DuckDB query.
    # Placeholder until data_loader and DuckDB integration are implemented.
    result = ToolResult(
        tool=ToolName.DATA_QUERY,
        step_number=step + 1,
        success=False,
        data=None,
        error="data_query tool not yet implemented — placeholder stub.",
    )

    return {"tool_results": [result]}


def run_data_query(
    table: str,
    filters: dict[str, object] | None = None,
    columns: list[str] | None = None,
    limit: int = 1000,
) -> list[dict]:
    """Execute a parameterised SELECT query via DuckDB and return rows as dicts.

    Args:
        table:   Name of the DuckDB table / view to query.
        filters: Column-to-value equality filters (ANDed together).
        columns: Columns to return; None means SELECT *.
        limit:   Maximum number of rows to return.

    Returns:
        List of row dicts.

    Raises:
        RuntimeError: If the query fails.

    Note:
        This function is intentionally *not* called by the placeholder node yet.
        It defines the interface that the node will use once the data layer is ready.
    """
    raise NotImplementedError("data_query tool not yet implemented.")
