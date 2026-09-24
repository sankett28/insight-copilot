"""
agent/validator.py
------------------
Centralized pre-execution validation boundary for AnalysisPlan objects.

Responsibilities:
  - Validate step sequence integrity (strictly 1..N contiguous, no duplicates).
  - Verify capability registration in Capability Registry.
  - Validate step parameters against each capability's Pydantic input schema.
  - Enforce dependency DAG rules (no cycles, no forward dependencies, no self-dependencies).
  - Check consistency between plan.steps and plan.selected_tools.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from models.schemas import AnalysisPlan, Intent
from utils.capability_registry import REGISTRY

logger = logging.getLogger(__name__)


@dataclass
class PlanValidationResult:
    """Encapsulates the result of pre-execution plan validation."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Append an error and mark validation as invalid."""
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        """Append an advisory warning without invalidating the plan."""
        self.warnings.append(message)


def validate_analysis_plan(plan: AnalysisPlan | None) -> PlanValidationResult:
    """Perform comprehensive structural and semantic validation on an AnalysisPlan.

    Args:
        plan: The AnalysisPlan instance produced by the planner node (or None).

    Returns:
        PlanValidationResult containing validity boolean and detailed diagnostic messages.
    """
    if plan is None:
        return PlanValidationResult(
            is_valid=False,
            errors=["Analysis plan is None."],
        )

    result = PlanValidationResult(is_valid=True)

    # 1. Conversational / Empty Step Handling
    if not plan.steps:
        if plan.selected_tools:
            result.add_error(
                f"Plan declares selected_tools {[t.value for t in plan.selected_tools]} but contains 0 execution steps."
            )
        return result

    # 2. Step Sequence Integrity (1..N contiguous, no duplicates)
    step_numbers = [s.step_number for s in plan.steps]
    seen_steps: set[int] = set()
    for idx, s in enumerate(plan.steps):
        if s.step_number in seen_steps:
            result.add_error(f"Duplicate step_number {s.step_number} found at step index {idx}.")
        seen_steps.add(s.step_number)

    expected_sequence = list(range(1, len(plan.steps) + 1))
    if step_numbers != expected_sequence:
        result.add_error(
            f"Step numbers must be strictly sequential from 1 to {len(plan.steps)}. Got: {step_numbers}"
        )

    # 3. Tool Registration & Parameter Validation
    for s in plan.steps:
        tool_name = s.tool.value if hasattr(s.tool, "value") else str(s.tool)
        if tool_name not in REGISTRY:
            result.add_error(f"Step {s.step_number}: Tool '{tool_name}' is not registered in Capability Registry.")
            continue

        cap = REGISTRY[tool_name]
        raw_params = s.parameters or {}

        # Check if any parameter value is a sentinel that will be resolved at
        # execution time (e.g. "__step_1_top_Region").  Sentinels are not real
        # values yet, so Pydantic validation against strict enumerations would
        # produce false-positive errors.  Skip value validation for such steps
        # and emit a warning instead.
        import re as _re
        _SENTINEL_PATTERN = _re.compile(r"^__step_\d+_(?:top|first)_.+$", _re.IGNORECASE)

        def _has_sentinel(obj) -> bool:
            if isinstance(obj, str):
                return bool(_SENTINEL_PATTERN.match(obj))
            if isinstance(obj, dict):
                return any(_has_sentinel(v) for v in obj.values())
            if isinstance(obj, list):
                return any(_has_sentinel(item) for item in obj)
            return False

        if _has_sentinel(raw_params):
            result.add_warning(
                f"Step {s.step_number} ({tool_name}) contains cross-step sentinel parameters "
                "that will be resolved at execution time; Pydantic value validation deferred."
            )
            continue

        try:
            cap.input_schema.model_validate(raw_params)
        except ValidationError as exc:
            result.add_error(
                f"Step {s.step_number} ({tool_name}) parameter validation failed: {exc.errors()}"
            )
        except Exception as exc:  # noqa: BLE001
            result.add_error(
                f"Step {s.step_number} ({tool_name}) parameter validation error: {exc}"
            )

    # 4. Dependency DAG Validity (no self-ref, no forward-ref, strictly dep < step_number)
    for s in plan.steps:
        if not s.depends_on:
            continue

        for dep in s.depends_on:
            if dep == s.step_number:
                result.add_error(f"Step {s.step_number} cannot depend on itself.")
            elif dep > s.step_number:
                result.add_error(
                    f"Step {s.step_number} contains forward dependency on step {dep}. Steps may only depend on strictly earlier steps."
                )
            elif dep not in seen_steps:
                result.add_error(
                    f"Step {s.step_number} depends on non-existent step {dep}."
                )

    # 5. Selected Tools Consistency Check
    step_tools = [s.tool for s in plan.steps]
    if plan.selected_tools != step_tools:
        result.add_warning(
            f"selected_tools mismatch: declared {[t.value for t in plan.selected_tools]} vs steps {[t.value for t in step_tools]}."
        )

    if not result.is_valid:
        logger.warning("Plan validation failed with %d error(s): %s", len(result.errors), result.errors)
    else:
        logger.info("Plan validation passed successfully (%d steps).", len(plan.steps))

    return result
