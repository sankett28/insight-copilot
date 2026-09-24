"""
utils/result_resolver.py
------------------------
Cross-step result parameter resolver for Insight Copilot.

Problem solved:
    When the planner emits a multi-step plan, Step N+1 may need a value that is
    only known after Step N executes (e.g. "filter to the top region found in
    Step 1").  The LLM cannot know this at plan time, so it either:
      - Hard-codes a guess (e.g. "North") that may be wrong.
      - Leaves the field blank, causing a validation error.

Solution — sentinel protocol:
    The planner emits a sentinel string in the parameters dict instead of a
    real value whenever a parameter must come from a prior step's results:

        "__step_<N>_top_<FIELD>"
            → Extract the value of <FIELD> from the first (top) row of
              Step N's tool result data.  Used when Step N is sorted DESC
              and the user wants the highest-ranked item.

        "__step_<N>_first_<FIELD>"
            → Synonym for __step_<N>_top_<FIELD>.

    Example parameter dict emitted by planner:
        {
          "metric": "Profit",
          "filters": {"Region": "__step_1_top_Region"}
        }

    After step 1 executes and returns [{"Region": "West", ...}, ...],
    resolve_step_parameters() replaces the sentinel with "West".

Usage:
    Call resolve_step_parameters(raw_params, tool_results) inside each tool
    node, BEFORE validating or executing the parameters.

    raw_params   — dict from plan_step.parameters
    tool_results — list[ToolResult] accumulated in AgentState so far

    Returns a new dict with all sentinels replaced by real values.
    If a sentinel cannot be resolved (step not done, field not found), the
    original sentinel string is left unchanged and a warning is logged so
    the tool validation layer will surface a meaningful error.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from models.schemas import ToolResult

logger = logging.getLogger(__name__)

# Pattern: __step_<N>_top_<FIELD>  or  __step_<N>_first_<FIELD>
_SENTINEL_RE = re.compile(
    r"^__step_(?P<step_n>\d+)_(?:top|first)_(?P<field>.+)$",
    re.IGNORECASE,
)


def resolve_step_parameters(
    raw_params: dict[str, Any],
    tool_results: list[ToolResult],
) -> dict[str, Any]:
    """Return a copy of *raw_params* with sentinel placeholders replaced.

    Iterates recursively through all string values in the parameter dict,
    including values nested inside other dicts (e.g. ``filters``).

    Args:
        raw_params:   The original parameters dict from the PlanStep.
        tool_results: Accumulated ToolResult list from AgentState.

    Returns:
        A new dict (shallow copy at the top level, deep copy of inner dicts)
        with sentinels substituted.  Non-sentinel values are untouched.
    """
    return _resolve_value(raw_params, tool_results)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _resolve_value(value: Any, tool_results: list[ToolResult]) -> Any:
    """Recursively resolve sentinels in a value."""
    if isinstance(value, dict):
        return {k: _resolve_value(v, tool_results) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, tool_results) for item in value]
    if isinstance(value, str):
        return _resolve_sentinel(value, tool_results)
    return value


def _resolve_sentinel(value: str, tool_results: list[ToolResult]) -> Any:
    """Attempt to resolve a single string value.  Returns original if not a sentinel."""
    m = _SENTINEL_RE.match(value)
    if m is None:
        return value  # Not a sentinel — pass through unchanged.

    step_n = int(m.group("step_n"))
    field = m.group("field")

    # Find the matching tool result
    matching: ToolResult | None = next(
        (tr for tr in tool_results if tr.step_number == step_n and tr.success),
        None,
    )

    if matching is None:
        logger.warning(
            "result_resolver: cannot resolve '%s' — step %d has no successful ToolResult yet.",
            value,
            step_n,
        )
        return value  # Leave sentinel; downstream validation will surface the error.

    data = matching.data
    if not data:
        logger.warning(
            "result_resolver: cannot resolve '%s' — step %d returned empty data.",
            value,
            step_n,
        )
        return value

    # Support list-of-dicts (most tool results) and plain dict
    if isinstance(data, list):
        first_row = data[0] if data else {}
    elif isinstance(data, dict):
        first_row = data
    else:
        logger.warning(
            "result_resolver: cannot resolve '%s' — step %d data is of unexpected type %s.",
            value,
            step_n,
            type(data).__name__,
        )
        return value

    # Case-insensitive field lookup
    resolved = None
    for key, val in first_row.items():
        if key.lower() == field.lower():
            resolved = val
            break

    if resolved is None:
        logger.warning(
            "result_resolver: field '%s' not found in step %d top row. Available keys: %s",
            field,
            step_n,
            list(first_row.keys()),
        )
        return value

    logger.info(
        "result_resolver: resolved '%s' → %r from step %d top row.",
        value,
        resolved,
        step_n,
    )
    print(
        f"[result_resolver] Resolved sentinel '{value}' → {resolved!r} "
        f"(from Step {step_n} top row field '{field}')"
    )
    return resolved
