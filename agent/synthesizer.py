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
from utils.logging_config import log_graph_completed, log_synthesis_completed
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
        run_id: str = state.get("run_id", "turn")
        telemetry = dict(state.get("telemetry", {}))
        timings = dict(telemetry.get("timings", {}))

        if errors and not tool_results:
            # Nothing useful came back; produce a safe error response.
            answer = (
                "I encountered an error while processing your request: "
                + "; ".join(errors)
                + ". Please try rephrasing your question."
            )
            print(f"[LangGraph: Synthesizer] Error state detected; returning safe error response.")
            return _build_output(answer, state.get("messages", []), telemetry=telemetry)

        print(f"\n[LangGraph: Synthesizer] Synthesizing {len(tool_results)} tool result(s)...")
        messages = _build_synthesizer_messages(query, tool_results, state)

        import time
        start_t = time.perf_counter()

        try:
            response = llm.chat(messages, temperature=0.3)
            answer = response.content
        except Exception as exc:  # noqa: BLE001
            print(f"[LangGraph: Synthesizer] ERROR: Synthesizer LLM call failed: {exc}")
            logger.exception("[%s] Synthesizer LLM call failed: %s", run_id, exc)
            answer = (
                "I was unable to generate a response due to an internal error. "
                "The raw tool results are available in the execution trace."
            )

        duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
        timings["synthesizer_ms"] = duration_ms
        if "start_time" in telemetry:
            timings["total_turn_ms"] = round((time.time() - telemetry["start_time"]) * 1000.0, 2)
        telemetry["timings"] = timings

        print(f"[LangGraph: Synthesizer] Final answer generated ({duration_ms:.2f}ms, {len(answer)} chars)")
        log_synthesis_completed(run_id=run_id, latency_ms=duration_ms)
        log_graph_completed(
            run_id=run_id,
            success=True,
            total_latency_ms=timings.get("total_turn_ms", duration_ms),
        )

        return _build_output(answer, state.get("messages", []), telemetry=telemetry)




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
        "Please synthesise these results into a clear, executive-level narrative. "
        "Strictly cite source steps e.g. [Step 1], [Step 2] for all numbers, totals, percentages, and metrics. "
        "Use only the verified numbers from the tool results — do not invent or extrapolate data."
    )

    messages_payload: list[dict[str, str]] = [
        {"role": "system", "content": SYNTHESIZER_SYSTEM_PROMPT}
    ]

    # Include recent conversation history (bounded to last 10 messages)
    raw_history = state.get("messages", [])
    if raw_history:
        # Prior messages excluding current query if it is the last item
        prior_messages = raw_history[:-1] if len(raw_history) > 1 else []
        for msg in prior_messages[-10:]:
            role_str = (
                msg.role.value
                if hasattr(msg, "role") and hasattr(msg.role, "value")
                else str(getattr(msg, "role", "user"))
            )
            content_str = getattr(msg, "content", "")
            if role_str in ("user", "assistant"):
                messages_payload.append({"role": role_str, "content": content_str})

    messages_payload.append({"role": "user", "content": user_content})
    return messages_payload


def _format_tool_results(tool_results: list[ToolResult]) -> str:
    """Serialise tool results to a human-readable string for the prompt.

    Includes step header, provenance (source_view, row_count, execution_time_ms),
    and truncates large list results (>15 rows) to keep prompt token size bounded.
    """
    if not tool_results:
        return "No tool results available."

    parts: list[str] = []
    for result in tool_results:
        status = "✓" if result.success else "✗"
        
        data = result.data
        truncation_note = ""
        if isinstance(data, list) and len(data) > 15:
            total_rows = len(data)
            data = data[:15]
            truncation_note = f"\n(Showing first 15 of {total_rows} rows)"

        data_repr = (
            json.dumps(data, default=str, indent=2)
            if data is not None
            else "null"
        )
        
        provenance = (
            f"(source: {result.source_view}, rows: {result.row_count}, time: {result.execution_time_ms}ms)"
        )
        header = f"[Step {result.step_number} | {result.tool.value}] {status} {provenance}"
        parts.append(f"{header}\n{data_repr}{truncation_note}")

    return "\n\n".join(parts)


def _build_output(
    answer: str,
    existing_messages: list[Message] | None = None,
    telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Package the synthesizer output into a state-patch dict preserving conversation history."""
    assistant_message = Message(role=Role.ASSISTANT, content=answer)
    messages = list(existing_messages or [])
    messages.append(assistant_message)
    patch: dict[str, Any] = {
        "final_answer": answer,
        "messages": messages,
    }
    if telemetry is not None:
        patch["telemetry"] = telemetry
    return patch



