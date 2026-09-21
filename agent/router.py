"""
agent/router.py
---------------
Router node for the LangGraph StateGraph.

Responsibility:
  Inspect the current execution state (selected_tools + current_step) and
  return the name of the next node to execute.  This is used as the
  conditional edge function in LangGraph.

The router is *purely deterministic* — it reads from the plan and dispatches
to the correct tool node.  No LLM calls happen here.
"""

from __future__ import annotations

import logging

from agent.state import AgentState
from models.schemas import ToolName

logger = logging.getLogger(__name__)

# Map from ToolName enum to the LangGraph node name string.
_TOOL_NODE_MAP: dict[ToolName, str] = {
    ToolName.DATA_QUERY: "data_query",
    ToolName.METRICS: "metrics",
    ToolName.TRENDS: "trends",
    ToolName.CHARTS: "charts",
}

# Sentinel returned when all steps are complete.
SYNTHESIZER_NODE = "synthesizer"
ERROR_NODE = "error_handler"


def router_node(state: AgentState) -> str:
    """LangGraph conditional-edge function: decide the next node to visit.

    Called by LangGraph after the router node itself has run (via
    ``graph.add_conditional_edges``).

    Reads:
        state["selected_tools"] — ordered tool list from the plan
        state["current_step"]   — index of the next tool to execute
        state["errors"]         — non-empty means something went wrong

    Returns:
        The string name of the next graph node.
    """
    errors: list[str] = state.get("errors", [])
    if errors:
        logger.warning("Router detected errors; routing to error_handler.")
        return ERROR_NODE

    selected_tools: list[ToolName] = state.get("selected_tools", [])
    current_step: int = state.get("current_step", 0)

    if not selected_tools:
        logger.info("No tools selected; routing directly to synthesizer.")
        return SYNTHESIZER_NODE

    if current_step >= len(selected_tools):
        logger.info("All %d tool steps complete; routing to synthesizer.", len(selected_tools))
        return SYNTHESIZER_NODE

    next_tool = selected_tools[current_step]
    node_name = _TOOL_NODE_MAP.get(next_tool)

    if node_name is None:
        logger.error("Unknown tool '%s'; cannot route.", next_tool)
        return ERROR_NODE

    logger.info(
        "Routing to '%s' (step %d/%d).",
        node_name,
        current_step + 1,
        len(selected_tools),
    )
    return node_name


def advance_step(state: AgentState) -> dict:
    """LangGraph node: increment current_step after a tool completes.

    This node is placed *after* each tool node in the graph so the router
    sees an updated step counter when it next evaluates.

    Reads:
        state["current_step"]

    Writes:
        current_step — incremented by 1
    """
    step = state.get("current_step", 0)
    return {"current_step": step + 1}
