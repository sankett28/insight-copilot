"""
agent/graph.py
--------------
LangGraph StateGraph definition for Insight Copilot.

This module is the single place where nodes, edges, and conditional routing
are wired together.  Keeping it separate from individual node implementations
makes the overall flow easy to reason about and test.

Conceptual flow:
    START
      ↓
    planner
      ↓
    router  ──────────────────────────────────────────┐
      │                                               │
      ├── data_query ──► step_advance ──► router      │
      ├── metrics    ──► step_advance ──► router      │
      ├── trends     ──► step_advance ──► router      │
      ├── charts     ──► step_advance ──► router      │
      ├── synthesizer ──────────────────────────────► END
      └── error_handler ───────────────────────────► END
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from agent.planner import build_planner_node
from agent.router import ERROR_NODE, SYNTHESIZER_NODE, advance_step, router_node
from agent.state import AgentState
from agent.synthesizer import build_synthesizer_node
from llm.base import BaseLLM
from tools.charts import charts_tool_node
from tools.compare import compare_tool_node
from tools.contribution import contribution_tool_node
from tools.data_profile import data_profile_tool_node
from tools.data_query import data_query_tool_node
from tools.metrics import metrics_tool_node
from tools.profitability import profitability_tool_node
from tools.trends import trends_tool_node
from tools.variance import variance_tool_node

logger = logging.getLogger(__name__)

# Node name constants — single source of truth.
NODE_PLANNER = "planner"
NODE_ROUTER = "router"
NODE_STEP_ADVANCE = "step_advance"
NODE_DATA_QUERY = "data_query"
NODE_DATA_PROFILE = "data_profile"
NODE_METRICS = "metrics"
NODE_TRENDS = "trends"
NODE_COMPARE = "compare"
NODE_CONTRIBUTION = "contribution"
NODE_PROFITABILITY = "profitability"
NODE_VARIANCE = "variance"
NODE_CHARTS = "charts"
NODE_SYNTHESIZER = SYNTHESIZER_NODE
NODE_ERROR = ERROR_NODE

# All tool nodes the router can dispatch to.
_TOOL_NODES: list[str] = [
    NODE_DATA_QUERY,
    NODE_DATA_PROFILE,
    NODE_METRICS,
    NODE_TRENDS,
    NODE_COMPARE,
    NODE_CONTRIBUTION,
    NODE_PROFITABILITY,
    NODE_VARIANCE,
    NODE_CHARTS,
]


def build_graph(llm: BaseLLM) -> StateGraph:
    """Construct and compile the Insight Copilot agent graph.

    Args:
        llm: Configured :class:`~llm.base.BaseLLM` instance shared by nodes
             that require LLM access (planner, synthesizer).

    Returns:
        A compiled LangGraph ``StateGraph`` ready to invoke.
    """
    graph = StateGraph(AgentState)

    # ------------------------------------------------------------------
    # Register nodes
    # ------------------------------------------------------------------
    graph.add_node(NODE_PLANNER, build_planner_node(llm))
    graph.add_node(NODE_ROUTER, _passthrough_node)  # routing logic lives in the edge
    graph.add_node(NODE_STEP_ADVANCE, advance_step)
    graph.add_node(NODE_DATA_QUERY, data_query_tool_node)
    graph.add_node(NODE_DATA_PROFILE, data_profile_tool_node)
    graph.add_node(NODE_METRICS, metrics_tool_node)
    graph.add_node(NODE_TRENDS, trends_tool_node)
    graph.add_node(NODE_COMPARE, compare_tool_node)
    graph.add_node(NODE_CONTRIBUTION, contribution_tool_node)
    graph.add_node(NODE_PROFITABILITY, profitability_tool_node)
    graph.add_node(NODE_VARIANCE, variance_tool_node)
    graph.add_node(NODE_CHARTS, charts_tool_node)
    graph.add_node(NODE_SYNTHESIZER, build_synthesizer_node(llm))
    graph.add_node(NODE_ERROR, _error_handler_node)

    # ------------------------------------------------------------------
    # Static edges
    # ------------------------------------------------------------------
    graph.add_edge(START, NODE_PLANNER)
    graph.add_edge(NODE_PLANNER, NODE_ROUTER)

    # After each tool runs, advance the step counter then re-evaluate routing.
    for tool_node in _TOOL_NODES:
        graph.add_edge(tool_node, NODE_STEP_ADVANCE)

    graph.add_edge(NODE_STEP_ADVANCE, NODE_ROUTER)

    # Terminal nodes.
    graph.add_edge(NODE_SYNTHESIZER, END)
    graph.add_edge(NODE_ERROR, END)

    # ------------------------------------------------------------------
    # Conditional edge: router decides next destination
    # ------------------------------------------------------------------
    graph.add_conditional_edges(
        NODE_ROUTER,
        router_node,
        {
            NODE_DATA_QUERY: NODE_DATA_QUERY,
            NODE_DATA_PROFILE: NODE_DATA_PROFILE,
            NODE_METRICS: NODE_METRICS,
            NODE_TRENDS: NODE_TRENDS,
            NODE_COMPARE: NODE_COMPARE,
            NODE_CONTRIBUTION: NODE_CONTRIBUTION,
            NODE_PROFITABILITY: NODE_PROFITABILITY,
            NODE_VARIANCE: NODE_VARIANCE,
            NODE_CHARTS: NODE_CHARTS,
            SYNTHESIZER_NODE: NODE_SYNTHESIZER,
            ERROR_NODE: NODE_ERROR,
        },
    )

    return graph.compile()


# ---------------------------------------------------------------------------
# Utility nodes
# ---------------------------------------------------------------------------


def _passthrough_node(state: AgentState) -> dict:
    """No-op node used for the router position in the graph.

    The actual routing decision is made by the conditional edge function
    (router_node), not by a node body.  This empty node gives LangGraph a
    concrete node to attach the conditional edge to.
    """
    return {}


def _error_handler_node(state: AgentState) -> dict:
    """Terminal error-handler node.

    Currently logs errors and returns an empty dict so the graph can reach END.
    In a future iteration this could produce a user-facing error message.
    """
    errors = state.get("errors", [])
    logger.error("Graph terminated with errors: %s", errors)
    if not state.get("final_answer"):
        return {
            "final_answer": (
                "I'm sorry, I encountered an error and could not complete your request. "
                + " | ".join(errors)
            )
        }
    return {}
