# Phase 2 Implementation Spec — Insight Copilot

**Branch**: `feat/phase-2-intelligent-agent`
**Depends on**: PR #4 (feat: complete phase 1 deterministic data layer and tools) merged to main
**Goal**: Transform the deterministic data foundation into a working end-to-end intelligent analytical agent

> This spec is the single source of truth for what Phase 2 builds.
> Nothing in Phase 2 requires redesigning Phase 1 architecture.
> Do NOT redesign `AgentState`, `LangGraph` graph structure, `PlanStep`, or the router logic.
> Do NOT touch Streamlit UI (Phase 3).

---

## Phase 1 Checklist — Verify Before Starting Phase 2

Confirm all of the following are true on the `main` branch before any Phase 2 work begins:

- [ ] `pytest tests/ -v` → 73 passed, 0 failed, no live API calls
- [ ] `data/Sales_Dataset_2024.xlsx` is present in the repo (or documented as required at setup)
- [ ] `utils/data_loader.py::validate_dataset()` returns `{"is_valid": True, "row_count": 2000, "column_count": 10}`
- [ ] `tools/metrics.py::execute_metrics_request()` is fully implemented (not a stub)
- [ ] `tools/trends.py::execute_trends_request()` is fully implemented (not a stub)
- [ ] `tools/data_query.py::execute_data_query_request()` is fully implemented (not a stub)
- [ ] `tools/charts.py::render_chart_from_data()` is fully implemented (not a stub)
- [ ] `PlanStep.parameters` is used by all 4 tool nodes (not parsed from `description`)
- [ ] Router validates `depends_on` before dispatching to a tool
- [ ] `create_initial_state()` resets per-turn execution fields cleanly

If any item is unchecked, fix it before opening a Phase 2 PR.

---

## Phase 2 Scope — What We Are Building

Phase 2 has **four concrete deliverables**:

```
1. Capability Registry        — the authoritative list of what the agent can do
2. data_profile capability    — "what does this dataset look like?"
3. Gemini planner live        — real API calls, validated planning accuracy
4. Five new analytical tools  — compare, contribution, profitability, variance (+ data_profile above)
```

Each deliverable has a strict boundary. They are not all-or-nothing — each can be
merged independently in sub-PRs if needed.

---

## Deliverable 1 — Capability Registry

### What it is

A single Python module that is the **authoritative inventory** of every capability
the agent can use. Currently the planner's system prompt and the router's dispatch
map list tools independently. The registry eliminates that duplication.

### File to create

`utils/capability_registry.py`

### Exact tasks

- [ ] Define a `Capability` dataclass with these fields:

  ```python
  @dataclass
  class Capability:
      name: str                         # canonical identifier, e.g. "metrics"
      category: str                     # "DATA_ACCESS" | "CORE_ANALYSIS" | "ADVANCED" | "PRESENTATION"
      description: str                  # one sentence for planner prompt injection
      input_schema: type[BaseModel]     # Pydantic model that validates PlanStep.parameters
      output_description: str           # what ToolResult.data will contain
      deterministic: bool               # True for all DuckDB/Plotly capabilities
      independent: bool                 # can run as first/only step (no prior ToolResult needed)
      consumes_previous_results: bool   # requires data from a prior ToolResult (e.g. charts)
      node_name: str                    # LangGraph node name for router dispatch
  ```

- [ ] Define `REGISTRY: dict[str, Capability]` — keyed by `capability.name`
- [ ] Register all **4 existing Phase 1 capabilities** in the registry:
  - `data_query` → `DataQueryRequest`, `node_name="data_query"`
  - `metrics` → `MetricsRequest`, `node_name="metrics"`
  - `trends` → `TrendsRequest`, `node_name="trends"`
  - `charts` → `ChartRequest`, `node_name="charts"`
- [ ] Implement `get_capability(name: str) -> Capability` — raises `KeyError` if not found
- [ ] Implement `get_planner_context() -> str` — returns formatted capability summary for planner system prompt injection
- [ ] Implement `get_node_map() -> dict[str, str]` — returns `{capability_name: node_name}` for router

### Update existing files

- [ ] `utils/prompts.py::PLANNER_SYSTEM_PROMPT` — replace the hard-coded tool list with a call to `get_planner_context()` (or inject it dynamically in `planner.py::_build_planner_messages`)
- [ ] `agent/router.py::_TOOL_NODE_MAP` — replace the hard-coded dict with `get_node_map()` at import time
- [ ] `agent/graph.py::_TOOL_NODES` — derive from `REGISTRY` instead of hard-coded list

### Do NOT do

- Do NOT make the registry a runtime service, HTTP API, or database.
- Do NOT add YAML/JSON config. Python dataclasses are sufficient.
- Do NOT break existing tests. All 73 tests must still pass after this change.

### Tests

- [ ] `tests/test_capability_registry.py`
  - [ ] All 4 Phase 1 capabilities are registered
  - [ ] `get_capability("metrics")` returns a `Capability` with correct fields
  - [ ] `get_capability("nonexistent")` raises `KeyError`
  - [ ] `get_planner_context()` returns a non-empty string containing each capability name
  - [ ] `get_node_map()` maps `"metrics"` → `"metrics"`, `"charts"` → `"charts"`, etc.
  - [ ] Router's dispatch map matches `get_node_map()` output
  - Minimum: 6 tests

### Acceptance criteria

- [ ] `pytest tests/test_capability_registry.py -v` → all pass
- [ ] `pytest tests/ -v` → still 73+ passed, 0 failed
- [ ] `agent/router.py` no longer contains a hand-written `_TOOL_NODE_MAP` dict literal

---

## Deliverable 2 — `data_profile` Capability

### What it answers

> "What does this dataset look like?"

This capability gives the agent (and ultimately the user) a complete picture
of the dataset before any analysis begins. It surfaces data quality issues as
observable evidence, not silent corrections.

### File to create

`tools/data_profile.py`

### Exact output contract

`ToolResult.data` must be a single dict (not a list) with this structure:

```python
{
    "dataset_name": "Sales_Dataset_2024",
    "row_count": 2000,
    "column_count": 10,
    "date_range": {
        "min": "2024-01-01",
        "max": "2024-12-31"
    },
    "numeric_summary": {
        "Revenue":    {"min": float, "max": float, "mean": float, "stddev": float},
        "Cost":       {"min": float, "max": float, "mean": float, "stddev": float},
        "Profit":     {"min": float, "max": float, "mean": float, "stddev": float},
        "Units_Sold": {"min": float, "max": float, "mean": float, "stddev": float},
        "Unit_Price": {"min": float, "max": float, "mean": float, "stddev": float}
    },
    "categorical_cardinality": {
        "Region":      int,  # distinct count
        "Category":    int,
        "Product":     int,
        "Salesperson": int
    },
    "null_counts": {
        "Date": int, "Region": int, "Product": int,   # 0 for clean dataset
        "Salesperson": int, "Units_Sold": int, "Unit_Price": int,
        "Category": int, "Revenue": int, "Cost": int, "Profit": int
    },
    "data_quality_warnings": [
        # list of strings, one per finding
        # e.g. "7 rows contain negative Profit"
        # e.g. "0 duplicate rows detected"
        # Empty list [] if dataset is fully clean
    ]
}
```

### Exact tasks

- [ ] `DataProfileRequest` Pydantic schema in `models/schemas.py`:
  ```python
  class DataProfileRequest(BaseModel):
      """No required parameters — profiles the full registered dataset view."""
      pass
  ```
- [ ] Add `DATA_PROFILE = "data_profile"` to `ToolName` enum in `models/schemas.py`
- [ ] `execute_data_profile() -> dict` in `tools/data_profile.py`:
  - [ ] `SELECT COUNT(*) FROM dataset` → `row_count`
  - [ ] `DESCRIBE dataset` → `column_count`
  - [ ] `SELECT MIN(Date)::VARCHAR, MAX(Date)::VARCHAR FROM dataset` → `date_range`
  - [ ] For each numeric column (`NUMERIC_COLUMNS`): `SELECT MIN(col), MAX(col), AVG(col), STDDEV(col) FROM dataset`
  - [ ] For each categorical column (`CATEGORICAL_COLUMNS`): `SELECT COUNT(DISTINCT col) FROM dataset`
  - [ ] For each column in `CANONICAL_COLUMNS`: `SELECT COUNT(*) FROM dataset WHERE col IS NULL` → `null_counts`
  - [ ] Data quality checks (append string to `data_quality_warnings` if count > 0):
    - `SELECT COUNT(*) FROM dataset WHERE Profit < 0`
    - `SELECT COUNT(*) FROM dataset WHERE Revenue <= 0`
    - Duplicate detection: compare `COUNT(*)` vs `COUNT(DISTINCT Date, Region, Product, Salesperson)`
  - [ ] Return assembled dict
- [ ] `data_profile_tool_node(state: AgentState) -> dict` in `tools/data_profile.py`
- [ ] Register `data_profile` in `REGISTRY`
- [ ] Add `"data_profile"` to router dispatch
- [ ] Wire `data_profile_tool_node` in `agent/graph.py`

### Do NOT do

- Do NOT clean, modify, or drop rows based on quality findings.
- Do NOT silently suppress quality warnings.
- Do NOT query any column not in `CANONICAL_COLUMNS`.

### Tests — `tests/test_data_profile.py`

- [ ] `execute_data_profile()` returns a `dict` (not a `list`)
- [ ] `row_count` equals 2000
- [ ] `column_count` equals 10
- [ ] `date_range["min"]` and `date_range["max"]` are non-null strings
- [ ] `numeric_summary` contains exactly the 5 keys in `NUMERIC_COLUMNS`
- [ ] Each numeric summary entry has `min`, `max`, `mean`, `stddev`
- [ ] `categorical_cardinality` contains exactly the 4 keys in `CATEGORICAL_COLUMNS`
- [ ] `null_counts` has one entry per column in `CANONICAL_COLUMNS` (10 keys)
- [ ] `data_quality_warnings` is a list (may be empty — that's fine)
- [ ] `data_profile_tool_node` returns `ToolResult(success=True)` on a valid plan step
- [ ] Minimum: 10 tests

### Acceptance criteria

- [ ] `pytest tests/test_data_profile.py -v` → all pass
- [ ] `pytest tests/ -v` → all pass
- [ ] `execute_data_profile()["row_count"]` == 2000 when run interactively

---

## Deliverable 3 — Gemini Planner Integration

> **Requires `GEMINI_API_KEY`** — these tests are excluded from the default offline suite.

### What we are validating

The planner currently exists as a skeleton. Phase 2 makes it real:
the LLM must produce correct `AnalysisPlan` objects with valid `PlanStep.parameters`
for real natural-language queries about `Sales_Dataset_2024`.

### Exact tasks

**`GeminiLLM` improvement**

- [ ] Migrate `GeminiLLM.chat()` from flat-prompt string to `genai.ChatSession`
- [ ] Remove the `# TODO` comment in `llm/gemini.py`
- [ ] Write a unit test verifying the chat history is sent correctly (mocked session)

**Planner prompt**

- [ ] `PLANNER_SYSTEM_PROMPT` (or dynamic injection) must include:
  - Each capability's name, description, and required parameter keys
  - The canonical column names and their roles (`get_schema_description().to_prompt_summary()` already provides this)
  - Instruction: "Parameters must conform exactly to the capability's input schema"

**Integration test script** — `tests/integration/test_planner_live.py`

- [ ] 15 representative queries (see `docs/development-plan.md` for the list)
- [ ] Uses `pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="No API key")`
- [ ] Each query asserts: valid `AnalysisPlan` returned, `intent` matches expected, `PlanStep.parameters` non-empty for parameterised tools
- [ ] Target: ≥13/15 pass

**Multi-turn test** — `tests/integration/test_multiturn_live.py`

- [ ] Turn 1: "What is revenue by region?" → regions appear in `final_answer`
- [ ] Turn 2: "Which of those has the highest profit?" → agent resolves context from Turn 1
- [ ] Turn 3: "Show me a chart of it" → `chart_artifacts` is non-empty

### Acceptance criteria

- [ ] Offline test suite unaffected (no API key required)
- [ ] ≥13/15 live planning queries correct
- [ ] `GeminiLLM` has no `TODO` comments

---

## Deliverable 4 — New Analytical Capabilities

### 4A — `compare`

**File**: `tools/compare.py`

**Schema** (`models/schemas.py`):
```python
class CompareRequest(BaseModel):
    metric: str                                                  # NUMERIC_COLUMNS
    aggregation: Literal["sum", "avg", "count", "min", "max"] = "sum"
    dimension: str                                               # e.g. "Region", "Category"
    value_a: str                                                 # e.g. "North"
    value_b: str                                                 # e.g. "South"
    filters: dict[str, Any] | None = None
```

**Output**:
```python
{
    "metric": "Revenue", "aggregation": "sum", "dimension": "Region",
    "entity_a": {"label": "North", "value": 425000.0},
    "entity_b": {"label": "South", "value": 318000.0},
    "absolute_delta": 107000.0,
    "pct_delta": 33.6    # None if entity_b.value == 0
}
```

**Tasks**:
- [ ] `CompareRequest` in `models/schemas.py` with `metric` validator
- [ ] `COMPARE = "compare"` in `ToolName`
- [ ] `execute_compare()` — two filtered aggregations + delta computation with zero-division guard
- [ ] `compare_tool_node`; register; wire in graph
- [ ] `tests/test_compare.py` — 8+ tests (region vs region, category vs category, delta values, zero guard, invalid inputs)

---

### 4B — `contribution`

**File**: `tools/contribution.py`

**Schema**:
```python
class ContributionRequest(BaseModel):
    metric: str                                     # NUMERIC_COLUMNS
    dimension: str                                  # group-by column
    aggregation: Literal["sum", "avg"] = "sum"
    filters: dict[str, Any] | None = None
    limit: int | None = Field(default=None, ge=1, le=50)
```

**Output**:
```python
[
    {"Region": "North", "sum_Revenue": 425000.0, "pct_of_total": 38.2},
    ...  # ordered desc, pct_of_total sum ≈ 100.0
]
```

**SQL pattern**:
```sql
SELECT dimension,
       SUM(metric) AS val,
       SUM(metric) * 100.0 / SUM(SUM(metric)) OVER () AS pct_of_total
FROM dataset
GROUP BY dimension
ORDER BY val DESC
LIMIT N
```

**Tasks**:
- [ ] `ContributionRequest` in `models/schemas.py`
- [ ] `CONTRIBUTION = "contribution"` in `ToolName`
- [ ] `execute_contribution()` — window function for percentage share
- [ ] `contribution_tool_node`; register; wire
- [ ] `tests/test_contribution.py` — 8+ tests (row counts, pct sum ≈ 100.0, descending order, limit, invalid inputs)

---

### 4C — `profitability`

**File**: `tools/profitability.py`

**Schema**:
```python
class ProfitabilityRequest(BaseModel):
    dimension: str                                  # group-by column
    filters: dict[str, Any] | None = None
    limit: int = Field(default=20, ge=1, le=100)
    sort_by: Literal["profit_margin_pct", "Revenue", "Profit", "Cost"] = "profit_margin_pct"
```

**Output**:
```python
[
    {
        "Product": "Widget A",
        "sum_Revenue": 84000.0, "sum_Cost": 52000.0, "sum_Profit": 32000.0,
        "profit_margin_pct": 38.1    # = sum_Profit / sum_Revenue * 100; None if Revenue = 0
    }
]
```

**SQL pattern**:
```sql
SELECT dimension,
       SUM(Revenue) AS sum_Revenue,
       SUM(Cost)    AS sum_Cost,
       SUM(Profit)  AS sum_Profit,
       SUM(Profit) / NULLIF(SUM(Revenue), 0) * 100 AS profit_margin_pct
FROM dataset
GROUP BY dimension
ORDER BY <sort_by> DESC
LIMIT N
```

**Tasks**:
- [ ] `ProfitabilityRequest` in `models/schemas.py`
- [ ] `PROFITABILITY = "profitability"` in `ToolName`
- [ ] `execute_profitability()` — with `NULLIF` zero-division guard; no conflation of revenue with margin
- [ ] `profitability_tool_node`; register; wire
- [ ] `tests/test_profitability.py` — 8+ tests (margin formula, zero-revenue guard, sort order, highest-revenue ≠ highest-margin assertion)

---

### 4D — `variance`

**File**: `tools/variance.py`

**Schema**:
```python
class VarianceRequest(BaseModel):
    metric: str                                                       # NUMERIC_COLUMNS
    granularity: Literal["day", "week", "month", "quarter", "year"] = "month"
    group_by: str | None = None
    filters: dict[str, Any] | None = None
```

**Output**:
```python
[
    {"period": "2024-01", "total_Revenue": 185000.0,
     "prev_Revenue": None, "absolute_change": None, "pct_change": None},
    {"period": "2024-02", "total_Revenue": 203000.0,
     "prev_Revenue": 185000.0, "absolute_change": 18000.0, "pct_change": 9.73},
    ...
]
```

**SQL pattern**:
```sql
WITH series AS (
    SELECT DATE_TRUNC('<granularity>', Date)::VARCHAR AS period,
           SUM(<metric>) AS total_val
    FROM dataset
    WHERE <filters>
    GROUP BY 1
    ORDER BY 1
)
SELECT period, total_val,
       LAG(total_val) OVER (ORDER BY period) AS prev_val,
       total_val - LAG(total_val) OVER (ORDER BY period) AS absolute_change,
       (total_val - LAG(total_val) OVER (ORDER BY period))
         / NULLIF(LAG(total_val) OVER (ORDER BY period), 0) * 100 AS pct_change
FROM series
```

**Tasks**:
- [ ] `VarianceRequest` in `models/schemas.py`
- [ ] `VARIANCE = "variance"` in `ToolName`
- [ ] `execute_variance()` — CTE + LAG window; first row always has `None` deltas
- [ ] `variance_tool_node`; register; wire
- [ ] `tests/test_variance.py` — 8+ tests (≥12 monthly rows, first row None, delta values, pct_change zero guard, quarter=4 rows, filter, invalid metric)

---

## Implementation Order

Follow this exact sequence. Run `pytest tests/ -v` after each step.

```
Step 1  Capability Registry      →  tests/test_capability_registry.py  →  pytest passes
Step 2  data_profile             →  tests/test_data_profile.py          →  pytest passes
Step 3  compare                  →  tests/test_compare.py               →  pytest passes
Step 4  contribution             →  tests/test_contribution.py          →  pytest passes
Step 5  profitability            →  tests/test_profitability.py         →  pytest passes
Step 6  variance                 →  tests/test_variance.py              →  pytest passes
Step 7  GeminiLLM ChatSession    →  unit test (mocked)                  →  pytest passes
Step 8  Integration tests        →  tests/integration/ (live API)       →  manual run
```

---

## Files to Create

| File | Purpose |
|---|---|
| `utils/capability_registry.py` | Authoritative capability inventory |
| `tools/data_profile.py` | data_profile capability |
| `tools/compare.py` | compare capability |
| `tools/contribution.py` | contribution capability |
| `tools/profitability.py` | profitability capability |
| `tools/variance.py` | variance capability |
| `tests/test_capability_registry.py` | Registry unit tests |
| `tests/test_data_profile.py` | data_profile unit tests |
| `tests/test_compare.py` | compare unit tests |
| `tests/test_contribution.py` | contribution unit tests |
| `tests/test_profitability.py` | profitability unit tests |
| `tests/test_variance.py` | variance unit tests |
| `tests/integration/__init__.py` | Package marker |
| `tests/integration/test_planner_live.py` | 15-query live planner validation |
| `tests/integration/test_multiturn_live.py` | Multi-turn context validation |

---

## Files to Modify

| File | Change |
|---|---|
| `models/schemas.py` | Add 5 new `ToolName` values; add 5 new request schemas |
| `agent/router.py` | Replace `_TOOL_NODE_MAP` literal with `get_node_map()` |
| `agent/graph.py` | Wire 5 new tool nodes; derive node list from registry |
| `utils/prompts.py` | Inject capability context from `get_planner_context()` |
| `llm/gemini.py` | Migrate `chat()` to `ChatSession`; remove TODO |

---

## Files to NOT Touch

`agent/state.py`, `agent/planner.py`, `agent/synthesizer.py`,
`tools/data_query.py`, `tools/metrics.py`, `tools/trends.py`, `tools/charts.py`,
`utils/data_loader.py`, `app.py`,
all existing Phase 1 test files.

---

## PR Strategy

**PR #6** — `feat/phase-2a-capability-registry-and-data-profile`
- Capability Registry + all existing-tool registrations
- `data_profile` capability + tests
- `GeminiLLM` ChatSession migration
- All schema additions for `DATA_PROFILE`

**PR #7** — `feat/phase-2b-analytical-capabilities`
- `compare`, `contribution`, `profitability`, `variance` + tests
- Integration test scripts
- Documentation updates

---

## Phase 2 Complete — Final Acceptance Criteria

- [ ] `pytest tests/ -v` (offline) → ≥100 tests pass, 0 fail
- [ ] `pytest tests/integration/ -v` (live API) → ≥13/15 planner queries correct
- [ ] `agent/router.py` contains no hand-written tool name map literal
- [ ] `execute_data_profile()["row_count"]` == 2000
- [ ] `sum(row["pct_of_total"] for row in execute_contribution(...))` ≈ 100.0
- [ ] Highest-margin group ≠ highest-revenue group in profitability output (real data)
- [ ] First row of `execute_variance(...)` has `absolute_change = None`
- [ ] `GeminiLLM` has no `# TODO` comments
- [ ] No Superstore schema references anywhere in the codebase or tests
