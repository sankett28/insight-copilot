"""
agent/router.py
---------------
Router node for the LangGraph StateGraph.

Responsibility:
  Inspect current execution state (plan, selected_tools, current_step, tool_results)
  and return the name of the next node to execute.

The router is purely deterministic. No LLM calls happen here.
"""

from __future__ import annotations

import logging

from agent.state import AgentState
from models.schemas import ToolName, ToolResult
from utils.capability_registry import get_node_map

logger = logging.getLogger(__name__)

# Map from ToolName enum to the LangGraph node name string, generated from capability registry.
_TOOL_NODE_MAP: dict[ToolName, str] = get_node_map()

SYNTHESIZER_NODE = "synthesizer"
ERROR_NODE = "error_handler"


def router_node(state: AgentState) -> str:
    """LangGraph conditional-edge function: decide the next node to visit.

    Reads:
        state["plan"]           — AnalysisPlan
        state["selected_tools"] — ordered tool list from the plan
        state["current_step"]   — index of the active tool step
        state["tool_results"]   — accumulated results
        state["errors"]         — non-empty means error encountered

    Returns:
        The string name of the next graph node.
    """
    errors: list[str] = state.get("errors", [])
    if errors:
        print(f"[LangGraph: Router] Errors detected -> Routing to {ERROR_NODE}: {errors}")
        logger.warning("Router detected errors; routing to error_handler: %s", errors)
        return ERROR_NODE

    selected_tools: list[ToolName] = state.get("selected_tools", [])
    current_step: int = state.get("current_step", 0)
    plan = state.get("plan")

    if not selected_tools or plan is None:
        print(f"[LangGraph: Router] No tools or plan -> Routing to {SYNTHESIZER_NODE}")
        logger.info("No tools or plan; routing directly to synthesizer.")
        return SYNTHESIZER_NODE

    if current_step >= len(selected_tools) or current_step >= len(plan.steps):
        print(f"[LangGraph: Router] All {len(selected_tools)} steps complete -> Routing to {SYNTHESIZER_NODE}")
        logger.info("All %d tool steps complete; routing to synthesizer.", len(selected_tools))
        return SYNTHESIZER_NODE

    current_plan_step = plan.steps[current_step]

    # Validate tool step dependencies
    if current_plan_step.depends_on:
        tool_results: list[ToolResult] = state.get("tool_results", [])
        for dep_step_num in current_plan_step.depends_on:
            dep_satisfied = any(
                tr.step_number == dep_step_num and tr.success for tr in tool_results
            )
            if not dep_satisfied:
                err_msg = (
                    f"Plan step {current_plan_step.step_number} ({current_plan_step.tool.value}) "
                    f"failed dependency check: required step {dep_step_num} was not completed successfully."
                )
                print(f"[LangGraph: Router] Dependency failure -> Routing to {ERROR_NODE}: {err_msg}")
                logger.error(err_msg)
                errors.append(err_msg)
                return ERROR_NODE

    next_tool = current_plan_step.tool
    node_name = _TOOL_NODE_MAP.get(next_tool)

    if node_name is None:
        print(f"[LangGraph: Router] Unknown tool '{next_tool}' -> Routing to {ERROR_NODE}")
        logger.error("Unknown tool '%s'; routing to error_handler.", next_tool)
        return ERROR_NODE

    print(
        f"[LangGraph: Router] Routing to node '{node_name}' (Step {current_step + 1}/{len(selected_tools)}: {current_plan_step.description})"
    )
    logger.info(
        "Routing to '%s' (step %d/%d | step_number=%d).",
        node_name,
        current_step + 1,
        len(selected_tools),
        current_plan_step.step_number,
    )
    return node_name



def advance_step(state: AgentState) -> dict:
    """LangGraph node: increment current_step after a tool completes."""
    step = state.get("current_step", 0)
    return {"current_step": step + 1}
