# Contributing to Insight Copilot

This document is the single source of truth for how we write code, name
branches, structure commits, and open pull requests in this repository.

Every contributor — including the project author — follows these rules.
They live in `CONTRIBUTING.md` so they are version-controlled alongside
the code they govern.

---

## Table of Contents

1. [Branching Strategy](#branching-strategy)
2. [Commit Conventions](#commit-conventions)
3. [Pull Request Workflow](#pull-request-workflow)
4. [Coding Standards](#coding-standards)
5. [Testing Requirements](#testing-requirements)
6. [Documentation Standards](#documentation-standards)

---

## 1. Branching Strategy

We follow a simplified **GitHub Flow**:

```
main  (always deployable, protected)
  └── <type>/<short-description>   (feature branches)
```

### Branch Naming

```
<type>/<short-description>
```

| Type | When to use |
|------|-------------|
| `feat/` | New feature or capability |
| `fix/` | Bug fix |
| `docs/` | Documentation only |
| `refactor/` | Code restructuring without behaviour change |
| `test/` | Adding or fixing tests |
| `chore/` | Tooling, config, dependencies |
| `data/` | Dataset-related changes |

**Examples**

```
feat/data-query-tool
feat/streamlit-chat-ui
fix/router-step-advance-off-by-one
docs/update-readme
refactor/llm-provider-abstraction
test/data-query-integration
chore/pin-langgraph-version
```

### Rules

- **Never commit directly to `main`.** All changes go through a PR.
- Branch from the latest `main` unless you are stacking on another branch.
- Delete your branch after it is merged.

---

## 2. Commit Conventions

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification.

### Format

```
<type>(<scope>): <short summary>

[optional body — explain WHY, not what]

[optional footer — BREAKING CHANGE / closes #issue]
```

### Types

| Type | Purpose |
|------|---------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation changes |
| `refactor` | Code change that neither adds a feature nor fixes a bug |
| `test` | Adding or updating tests |
| `chore` | Build/config changes that don't affect production code |
| `perf` | Performance improvement |
| `style` | Formatting only (no logic change) |

### Scope (optional)

Use the module or layer affected: `agent`, `tools`, `llm`, `models`, `utils`, `ui`, `tests`, `deps`.

### Short Summary Rules

- Use the imperative mood: *"add metric tool"* not *"added metric tool"*
- Maximum 72 characters
- No full stop at the end
- Must be meaningful — no *"update stuff"*, *"wip"*, *"fix"*

### Examples

```
feat(tools): implement data_query tool with DuckDB SELECT

Add run_data_query() using in-process DuckDB connection.
Supports column selection, equality filters, and row limits.

Closes #12
```

```
fix(router): correct off-by-one in step advance

current_step was post-incremented after the boundary check,
causing the final tool to be called twice on 3-step plans.
```

```
docs: rewrite README as professional engineering documentation

Replaces placeholder content with accurate Phase 0 status,
Mermaid architecture diagram, and full local setup guide.
```

```
test(router): add multi-step routing edge case tests
```

```
chore(deps): pin langgraph to 1.2.x to avoid breaking API changes
```

### Logical Commit Phases

Break work into **small, reviewable, logically isolated commits**.

| ❌ Bad | ✅ Good |
|--------|---------|
| One giant commit with everything | Separate commits per concern |
| `feat: add everything` | `feat(tools): implement data_query tool` |
| Mixing refactors with features | Separate `refactor` commit before `feat` |
| Mixing test + production code | `feat` commit followed by `test` commit |

A commit should pass all tests on its own (bisectable).

---

## 3. Pull Request Workflow

### When to Open a PR

Open a PR for **every change to `main`**, no exceptions.

### PR Title

Follow the same Conventional Commits format:

```
feat(tools): implement DuckDB data_query and metrics tools
```

### PR Description Template

Use this template every time:

```markdown
## Summary

One paragraph explaining what this PR does and why.

## Changes

- List of files changed and what changed in each
- Keep it at the file/function level

## Testing

How the changes were tested:
- [ ] All existing tests pass: `pytest tests/ -v`
- [ ] New tests added for new code
- [ ] Manually verified: [describe what you tested]

## Checklist

- [ ] Branch branched from latest `main`
- [ ] Follows commit conventions
- [ ] Type hints on all new functions
- [ ] Docstrings on all new public functions/classes
- [ ] No API keys or secrets in code
- [ ] `requirements.txt` updated if new dependencies added
- [ ] `docs/` updated if architecture or decisions changed
```

### Review Requirements

- At minimum, the author self-reviews before merging.
- For significant changes, request a peer review.
- No PR is merged with failing tests.

### Merging

- Use **Squash and Merge** for small, single-purpose PRs.
- Use **Merge Commit** for multi-commit PRs where the history is meaningful.
- Never force-push to `main`.

---

## 4. Coding Standards

### Python Version

Python **3.12+**. Use modern syntax (`match`, `type X = ...`) where it improves clarity.

### Type Hints

**All** functions must have type hints — parameters and return type.

```python
# ✅ Good
def compute_metric(table: str, column: str, agg: AggregationType) -> list[dict]:
    ...

# ❌ Bad
def compute_metric(table, column, agg):
    ...
```

Use `from __future__ import annotations` at the top of every module for
forward-reference support.

### Docstrings

All public functions, classes, and modules must have docstrings.
Use Google-style docstrings:

```python
def run_data_query(
    table: str,
    filters: dict[str, object] | None = None,
    limit: int = 1000,
) -> list[dict]:
    """Execute a parameterised SELECT query via DuckDB.

    Args:
        table:   DuckDB table or view name.
        filters: Column-to-value equality filters (ANDed together).
        limit:   Maximum number of rows returned.

    Returns:
        List of row dicts.

    Raises:
        RuntimeError: If the query fails.
    """
```

### Naming

| Thing | Convention | Example |
|-------|-----------|---------|
| Modules | `snake_case` | `data_query.py` |
| Classes | `PascalCase` | `GeminiLLM` |
| Functions | `snake_case` | `build_planner_node` |
| Constants | `UPPER_SNAKE_CASE` | `PLANNER_SYSTEM_PROMPT` |
| Enums | `PascalCase` class, `UPPER_SNAKE` members | `ToolName.DATA_QUERY` |

No magic strings. Use **enums or module constants** whenever a string value
is used more than once or has semantic meaning (node names, tool names,
intent types, SQL keywords).

### Module Size

- **Hard limit: 200 lines per module.** If you are approaching it, split.
- One clear responsibility per module.
- No circular imports — the dependency direction is:
  `models → llm → utils → tools → agent → app`

### Error Handling

- **Never silently swallow exceptions** with bare `except: pass`.
- Log every caught exception before re-raising or returning an error state.
- Tool nodes must return `ToolResult(success=False, error=str(exc))` rather
  than raising — the graph handles errors gracefully.
- Use `logger = logging.getLogger(__name__)` in every module.

### Environment Variables

- **No API keys in source code.** Ever.
- Use `python-dotenv` to load `.env` locally.
- The `.env` file is `.gitignore`d. `.env.example` is committed.

### Formatting

We target **PEP 8** compliance. Recommended formatter: `ruff format`.
Line length: **88 characters** (Black-compatible).

```bash
# Format all Python files
ruff format .

# Lint
ruff check .
```

Add `ruff` to the dev dependencies when adding linting to CI.

---

## 5. Testing Requirements

### Rules

- Every new function gets at least one test.
- Tests must be **independent** — no shared mutable state between tests.
- Tests must be **fast** — no live API calls, no file I/O to external services.
  Use mocks or in-memory DuckDB for data tests.
- All tests must pass before a PR can be merged.

### Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage report
pytest tests/ -v --cov=. --cov-report=term-missing

# Single file
pytest tests/test_router.py -v
```

### Test File Naming

```
tests/test_<module_name>.py
```

Mirrors the source module structure exactly.

### What to Test

| What | How |
|------|-----|
| Pure functions (router, schemas) | Direct unit tests |
| LangGraph nodes | Inject mock LLM, assert state changes |
| Tool nodes | Assert `ToolResult` fields |
| DuckDB tools | Use in-memory DuckDB with synthetic test data |
| LLM providers | Mock at the `BaseLLM` level |

---

## 6. Documentation Standards

### When to Update Docs

| Change | Required doc update |
|--------|-------------------|
| New tool | `docs/architecture.md` |
| New architecture decision | `docs/decisions.md` (new ADR) |
| Changed setup | `README.md` Local Setup section |
| New phase complete | `docs/development-plan.md` checkbox update |
| Changed status | `README.md` Development Status table |

### ADR Format

New architectural decisions go in `docs/decisions.md` as a new `ADR-NNN` section:

```markdown
## ADR-008 — Decision Title

**Date**: YYYY-MM-DD
**Status**: Accepted | Superseded by ADR-NNN | Deprecated

### Context
### Options considered
### Decision
### Rationale
```

### Accuracy Rule

Documentation must be **accurate to the current state of the code**.
Do not document features that are not yet implemented as if they exist.
Use *"planned"* or *"not yet implemented"* labels where appropriate.
