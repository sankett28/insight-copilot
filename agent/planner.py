"""
agent/planner.py
----------------
Planner node for the LangGraph StateGraph.

Responsibility:
  Given the current user query, conversation history, and dataset schema,
  call the LLM to produce a structured AnalysisPlan with typed tool parameters.
"""

from __future__ import annotations

import logging

from agent.state import AgentState
from agent.validator import validate_analysis_plan
from llm.base import BaseLLM
from models.schemas import AnalysisPlan, Intent, Message, Role, ToolName
from utils.capability_registry import get_planner_context
from utils.data_loader import get_schema_description
from utils.logging_config import log_planner_completed
from utils.prompts import PLANNER_SYSTEM_PROMPT


logger = logging.getLogger(__name__)


def build_planner_node(llm: BaseLLM):
    """Return a LangGraph-compatible node function bound to *llm*."""

    def planner_node(state: AgentState) -> dict:
        """LangGraph node: classify intent and produce an AnalysisPlan.

        Reads:
            state["query"]    — current user question
            state["messages"] — conversation history

        Writes:
            intent         — classified intent string
            plan           — AnalysisPlan instance
            selected_tools — ordered tool list derived from the plan
            current_step   — reset to 0
            errors         — validation or LLM errors if encountered
        """
        query: str = state.get("query", "")
        history: list[Message] = state.get("messages", [])

        if not query or not query.strip():
            logger.warning("planner_node received an empty query.")
            return {
                "intent": Intent.UNKNOWN.value,
                "plan": None,
                "selected_tools": [],
                "current_step": 0,
                "errors": ["Planner received an empty query."],
            }

        # Build message list for LLM call with dataset schema context
        print(f"\n[LangGraph: Planner] Processing user query: {query}")
        messages = _build_planner_messages(query, history)
        run_id = state.get("run_id", "turn")
        telemetry = dict(state.get("telemetry", {}))
        timings = dict(telemetry.get("timings", {}))

        import time
        start_t = time.perf_counter()

        try:
            plan: AnalysisPlan = llm.structured_chat(messages, AnalysisPlan)
        except Exception as exc:  # noqa: BLE001
            print(f"[LangGraph: Planner] ERROR: Planner LLM execution failed: {exc}")
            logger.exception("[%s] Planner LLM execution failed: %s", run_id, exc)
            return {
                "intent": Intent.UNKNOWN.value,
                "plan": None,
                "selected_tools": [],
                "current_step": 0,
                "errors": [f"Planner LLM failed to produce a structured plan: {exc}"],
            }

        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
        timings["planner_ms"] = duration_ms
        telemetry["timings"] = timings

        # Pre-execution Plan Validation Boundary
        validation = validate_analysis_plan(plan)
        if not validation.is_valid:
            print(f"[LangGraph: Planner] ERROR: Generated plan failed validation: {validation.errors}")
            logger.error("[%s] Generated plan failed validation: %s", run_id, validation.errors)
            return {
                "intent": plan.intent.value,
                "plan": plan,
                "selected_tools": [step.tool for step in plan.steps],
                "current_step": 0,
                "telemetry": telemetry,
                "errors": validation.errors,
            }

        # Always derive selected_tools directly from plan.steps so that
        # len(selected_tools) == len(plan.steps).  The LLM-generated
        # selected_tools field may be deduplicated (e.g. two metrics steps →
        # ["metrics"]) which would cause the router to terminate after step 1.
        # This is the canonical execution list; it overrides whatever the LLM
        # returned in the selected_tools field.
        derived_tools = [step.tool for step in plan.steps]

        print(
            f"[LangGraph: Planner] Plan produced ({duration_ms:.2f}ms): intent={plan.intent.value} | "
            f"steps={len(plan.steps)} | tools={[t.value for t in derived_tools]}"
        )
        log_planner_completed(
            run_id=run_id,
            intent=plan.intent.value,
            tools=[t.value for t in derived_tools],
            latency_ms=duration_ms,
        )

        return {
            "intent": plan.intent.value,
            "plan": plan,
            "selected_tools": derived_tools,
            "current_step": 0,
            "telemetry": telemetry,
        }



    return planner_node



def _build_planner_messages(
    query: str,
    history: list[Message],
) -> list[dict[str, str]]:
    """Assemble the message list sent to the LLM for planning."""
    schema_summary = get_schema_description().to_prompt_summary()
    capabilities_summary = get_planner_context()
    system_content = f"{PLANNER_SYSTEM_PROMPT}\n\n{schema_summary}\n\n{capabilities_summary}"

    msgs: list[dict[str, str]] = [
        {"role": "system", "content": system_content},
    ]

    # Include up to the last 10 turns to keep the prompt bounded.
    bounded_history = history[-10:] if history else []
    for msg in bounded_history:
        msgs.append({"role": msg.role.value, "content": msg.content})

    # Only append query if it is not already the trailing user message in history
    if not bounded_history or bounded_history[-1].role != Role.USER or bounded_history[-1].content != query:
        msgs.append({"role": "user", "content": query})

    return msgs

