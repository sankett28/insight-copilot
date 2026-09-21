"""
agent/synthesizer.py
--------------------
Synthesizer node for the LangGraph StateGraph.

Responsibility:
  Given the structured tool_results collected during this turn, call the LLM
  to produce an analyst-style final answer in natural language.

The synthesizer is the *only* place where the LLM touches tool output.  Its
job is narrative, not numerical: it must use *exactly* the numbers returned
by the tools — never fabricate or re-calculate them.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent.state import AgentState
from llm.base import BaseLLM
from models.schemas import Message, Role, ToolResult
from utils.prompts import SYNTHESIZER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def build_synthesizer_node(llm: BaseLLM):
    """Return a LangGraph-compatible synthesizer node bound to *llm*.

    Args:
        llm: Configured :class:`~llm.base.BaseLLM` instance.

    Returns:
        A callable ``synthesizer_node(state: AgentState) -> dict``.
    """

    def synthesizer_node(state: AgentState) -> dict:
        """LangGraph node: turn tool results into a final natural-language answer.

        Reads:
            state["query"]        — original user question
            state["plan"]         — the AnalysisPlan (for context / rationale)
            state["tool_results"] — list of ToolResult from each tool step
            state["errors"]       — any accumulated errors

        Writes:
            final_answer — analyst-style answer string
            messages     — appends the assistant reply to history
        """
        query: str = state.get("query", "")
        tool_results: list[ToolResult] = state.get("tool_results", [])
        errors: list[str] = state.get("errors", [])

        if errors and not tool_results:
            # Nothing useful came back; produce a safe error response.
            answer = (
                "I encountered an error while processing your request: "
                + "; ".join(errors)
                + ". Please try rephrasing your question."
            )
            return _build_output(answer, query)

        messages = _build_synthesizer_messages(query, tool_results, state)

        try:
            response = llm.chat(messages, temperature=0.3)
            answer = response.content
        except Exception as exc:  # noqa: BLE001
            logger.exception("Synthesizer LLM call failed: %s", exc)
            answer = (
                "I was unable to generate a response due to an internal error. "
                "The raw tool results are available in the execution trace."
            )

        return _build_output(answer, query)

    return synthesizer_node


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_synthesizer_messages(
    query: str,
    tool_results: list[ToolResult],
    state: AgentState,
) -> list[dict[str, str]]:
    """Assemble the message list sent to the LLM for synthesis."""
    plan = state.get("plan")
    plan_summary = ""
    if plan:
        plan_summary = (
            f"Execution plan: {plan.rationale}\n"
            f"Steps executed: {[s.tool.value for s in plan.steps]}"
        )

    results_text = _format_tool_results(tool_results)

    user_content = (
        f"User question: {query}\n\n"
        f"{plan_summary}\n\n"
        f"Tool results:\n{results_text}\n\n"
        "Please synthesise these results into a concise analyst-style answer. "
        "Use only the numbers from the tool results — do not invent any data."
    )

    return [
        {"role": "system", "content": SYNTHESIZER_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _format_tool_results(tool_results: list[ToolResult]) -> str:
    """Serialise tool results to a human-readable string for the prompt."""
    if not tool_results:
        return "No tool results available."

    parts: list[str] = []
    for result in tool_results:
        status = "✓" if result.success else "✗"
        data_repr = (
            json.dumps(result.data, default=str, indent=2)
            if result.data is not None
            else "null"
        )
        parts.append(
            f"[Step {result.step_number} | {result.tool.value}] {status}\n{data_repr}"
        )
    return "\n\n".join(parts)


def _build_output(answer: str, query: str) -> dict[str, Any]:
    """Package the synthesizer output into a state-patch dict."""
    assistant_message = Message(role=Role.ASSISTANT, content=answer)
    return {
        "final_answer": answer,
        "messages": [assistant_message],
    }
