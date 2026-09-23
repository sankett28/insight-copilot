## Description
This PR strengthens deterministic silent-correctness gates and acceptance test tooling:
1. **Citation Verification Gate**: Implements automated auditing of synthesizer citations (`[Step X]`) to strictly catch hallucinated step references.
2. **Deterministic Sequence & Tool Asserts**: Adds exact tool sequence validation and execution success gates per step.
3. **Runner Flexibility & CI Readiness**: Adds CLI flags (`--delay`, `--filter`, `--output`, `--dry-run`) to `scripts/acceptance_test_runner.py` allowing fast offline validation in CI environments without incurring live LLM costs.
4. **Automated Unit Tests**: Adds `tests/test_acceptance_runner.py` to ensure acceptance test contracts, citation audit logic, and dry-run execution are checked as part of `pytest`.

## Changes
- `scripts/acceptance_test_runner.py`: Added `evaluate_turn_checks`, citation validation, tool result verification, and CLI arguments.
- `tests/test_acceptance_runner.py`: New unit test suite for acceptance runner and silent-correctness evaluation.

## Verification
- `pytest tests/test_acceptance_runner.py -v`: 4 passed
- `pytest tests/ --ignore=tests/integration -v`: 172 passed
- `python scripts/acceptance_test_runner.py --dry-run`: 25/25 validated
