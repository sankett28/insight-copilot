# Development Plan — Insight Copilot

This is a **living engineering document**. Update it whenever implementation
progresses. A task is marked complete only when the implementation satisfies
its acceptance criteria and associated tests pass. The existence of a file
does not mean its implementation is complete.

---

## Phase 0 — Project Skeleton and Contracts

**Objective**: Establish the repository structure, typed interfaces, and test
harness before any live API or data calls are made.

### Status: ✅ Complete

### Tasks

- [x] Repository initialised and pushed to GitHub (`sankett28/insight-copilot`)
- [x] `.gitignore` — secrets, `.venv`, DuckDB files, dataset files excluded
- [x] `.gitattributes` — LF line endings enforced
- [x] `CONTRIBUTING.md` — branching strategy, commit conventions, coding standards
- [x] `requirements.txt` — all production and development dependencies
- [x] `.env.example` — template for all environment variables
- [x] Virtual environment (`.venv`) with all dependencies installed
- [x] `models/schemas.py` — Pydantic contracts: `Intent`, `ToolName`, `AnalysisPlan`, `PlanStep`, `ToolResult`, `Message`, `Role`, `ColumnMetadata`, `DatasetSchema`
- [x] `agent/state.py` — `AgentState` TypedDict; `create_initial_state` for turn isolation
- [x] `llm/base.py` — `BaseLLM` abstract interface with `chat()` and `structured_chat()`
- [x] `llm/gemini.py` — `GeminiLLM`: JSON mode for structured output, flat-prompt for chat
- [x] `llm/factory.py` — `create_llm()` factory with `LLMProvider` enum
- [x] `agent/planner.py` — planner node skeleton with error handling and history truncation
- [x] `agent/router.py` — `router_node` conditional edge + `advance_step` node
- [x] `agent/synthesizer.py` — synthesizer node with fallback behaviour
- [x] `agent/graph.py` — full `StateGraph` wiring: 9 nodes, static edges, conditional routing edge
- [x] `tools/data_query.py` — tool node + `DataQueryRequest` Pydantic contract
- [x] `tools/metrics.py` — tool node + `MetricsRequest` Pydantic contract + `AggregationType` enum
- [x] `tools/trends.py` — tool node + `TrendsRequest` Pydantic contract
- [x] `tools/charts.py` — tool node + `ChartRequest` Pydantic contract + `ChartType` enum
- [x] `utils/prompts.py` — `PLANNER_SYSTEM_PROMPT` and `SYNTHESIZER_SYSTEM_PROMPT`
- [x] `utils/data_loader.py` — `load_dataset()`, `get_schema()`, `get_connection()` interfaces
- [x] `app.py` — Streamlit shell: page config, sidebar, two-column layout
- [x] `.streamlit/config.toml` — dark theme configuration
- [x] `conftest.py` — project root on `sys.path` for pytest
- [x] `pytest.ini` — test discovery configuration
- [x] `tests/test_graph.py` — graph construction and node-set tests (mock LLM)
- [x] `tests/test_router.py` — router logic and step-advance tests (10 cases)
- [x] `tests/test_tools.py` — tool node contract tests (15 cases)
- [x] `docs/architecture.md` — field-level state docs, node IO tables, routing algorithm
- [x] `docs/decisions.md` — 8 ADRs
- [x] `docs/development-plan.md` — this document
- [x] `README.md` — engineering documentation

### Acceptance Criteria

- [x] `pytest tests/ -v` passes with 27 tests, 0 failures, no live API calls
- [x] Graph compiles and contains all 9 expected nodes
- [x] Router dispatches correctly for all tool types and edge cases
- [x] All tool stubs return `ToolResult` with correct `tool` and `step_number`
- [x] No API keys or secrets in any committed file
- [x] All public functions and classes have type hints and docstrings

---

## Phase 1 — Deterministic Data Foundation

**Objective**: Connect the canonical dataset (`Sales_Dataset_2024.xlsx`) to DuckDB
via a Parquet runtime and implement all four foundational analytical tool functions
so that the graph can execute a complete turn — excluding LLM integration — with
real computed results from real data.

### Status: ✅ Complete

### Canonical Dataset Contract

- **Source**: `data/Sales_Dataset_2024.xlsx`
- **Runtime**: `data/sales_dataset.parquet` (auto-generated on first run)
- **DuckDB View**: `dataset` (registered by `get_connection()` at startup)
- **Schema**: `Date`, `Region`, `Product`, `Salesperson`, `Units_Sold`, `Unit_Price`, `Category`, `Revenue`, `Cost`, `Profit`
- **Size**: 2,000 rows, 10 columns

### Tasks

**Data layer**

- [x] Excel → Parquet conversion (`ensure_parquet_dataset()`) with `Date` parsed as TIMESTAMP
- [x] Thread-safe in-process DuckDB connection cached at module level (`get_connection()`)
- [x] `reset_connection()` for clean test isolation
- [x] `validate_dataset()` — row count, column presence, type compatibility
- [x] `get_schema()` — returns `list[dict[str, str]]` from `DESCRIBE dataset`
- [x] `get_schema_description()` → `DatasetSchema` — structured metadata for LLM prompt injection
- [x] `ColumnMetadata` with `semantic_role`, `can_group`, `can_metric`, `can_time`
- [x] Schema constants in `models/schemas.py`: `DATE_COLUMN`, `CATEGORICAL_COLUMNS`, `NUMERIC_COLUMNS`, `CANONICAL_COLUMNS`

**`data_query` tool**

- [x] `DataQueryRequest` Pydantic contract — `columns`, `filters`, `sort_by`, `sort_order`, `limit (≤100)`
- [x] `execute_data_query_request()` — parameterised `SELECT` with column validation against `CANONICAL_COLUMNS`
- [x] `data_query_tool_node` — reads `plan.steps[current_step].parameters`, validates via Pydantic, appends `ToolResult`
- [x] `ToolResult(success=False, error=...)` on invalid columns, filters, or DuckDB exceptions

**`metrics` tool**

- [x] `MetricsRequest` Pydantic contract — `metric` (validated against `NUMERIC_COLUMNS`), `aggregation`, `group_by`, `filters`, `limit`, `sort`
- [x] `execute_metrics_request()` — DuckDB `GROUP BY` with `SUM` / `AVG` / `COUNT` / `MIN` / `MAX` / `MEDIAN` dispatch
- [x] Group column validation against `CANONICAL_COLUMNS`
- [x] Safe string filter parameterisation (quote escaping)
- [x] `metrics_tool_node` — reads plan step, validates, appends `ToolResult`

**`trends` tool**

- [x] `TrendsRequest` Pydantic contract — `metric`, `date_column` (validated as `Date`), `granularity`, `group_by`, `filters`
- [x] `execute_trends_request()` — `DATE_TRUNC(granularity, Date)` with `SUM` aggregation, ordered by period
- [x] Granularities: `day`, `week`, `month`, `quarter`, `year`
- [x] Optional `group_by` dimension with column validation
- [x] `trends_tool_node` — reads plan step, validates, appends `ToolResult`

**`charts` tool**

- [x] `ChartRequest` Pydantic contract — `chart_type`, `x`, `y`, `color`, `title`
- [x] `render_chart_from_data()` — Plotly `bar`, `line`, `scatter` via `plotly.express`
- [x] Dark theme via `template="plotly_dark"`
- [x] Output: `fig.to_dict()` stored in `ToolResult.data` and `chart_artifacts`
- [x] `charts_tool_node` — resolves data source from `depends_on` or most recent successful `ToolResult` with list data; does NOT query DuckDB
- [x] Column auto-inference when `x`/`y` not specified in parameters

**PlanStep parameter integration**

- [x] Structured `parameters: dict[str, Any]` field on `PlanStep` validated at tool node entry
- [x] All tool nodes read from `plan.steps[current_step].parameters`
- [x] `model_validate(raw_params)` with controlled `ToolResult(success=False)` on validation failure

**Router dependency validation**

- [x] `depends_on` validation in `router_node`: for each declared dependency, a successful `ToolResult` must exist
- [x] Failed dependency routes to `error_handler` with a descriptive error message

### Tests Implemented

- [x] `tests/test_data_layer.py` — 10 tests: path resolution, Excel→Parquet, view creation, schema retrieval, column validation, row count (2,000), TIMESTAMP type, `validate_dataset()`
- [x] `tests/test_data_query.py` — 10 tests: column selection, equality filters, multi-filter, sorting, limit capping (max 100), invalid columns, malformed parameters
- [x] `tests/test_metrics.py` — 12 tests: total revenue sum, region/category groupby, avg unit price, min/max, count, filter, sort, invalid metric column, malformed parameters; all with numerical value assertions
- [x] `tests/test_trends.py` — 8 tests: monthly revenue/profit, region filter, category groupby, quarter/year granularity, invalid date column, malformed request
- [x] `tests/test_charts.py` — 7 tests: bar/line/scatter render, x/y mapping, Plotly dict serialisation, auto-column inference, missing-data error path; zero Streamlit import
- [x] `tests/test_graph.py`, `tests/test_router.py`, `tests/test_tools.py` — 30 existing tests all passing

**Total**: 73 tests passing. Zero live API calls. Zero Streamlit dependency.

### Acceptance Criteria

- [x] `load_dataset()` completes without error and registers `dataset` DuckDB view
- [x] `validate_dataset()` returns `{"is_valid": True, "row_count": 2000, "column_count": 10}`
- [x] `compute_metric("Revenue", "sum", group_by="Region")` returns 4 rows with correct values
- [x] `compute_trend("Revenue", granularity="month")` returns 12 monthly rows
- [x] `render_chart(data, ChartType.BAR, x="Region", y="sum_Revenue")` returns non-empty Plotly dict
- [x] All tool nodes return `ToolResult(success=True)` when called with valid plan step parameters
- [x] Malformed parameters return `ToolResult(success=False, error=...)` without crashing the graph
- [x] Full test suite: `pytest tests/ -v` → 73 passed, 0 failed

---

## Phase 2 — Intelligent Analytical Agent

**Objective**: Transform the deterministic data foundation into a working end-to-end
intelligent agent. The Gemini planner must produce correct, structured `AnalysisPlan`
objects for real natural-language queries. New analytical capabilities must extend
the agent's investigative reach. The synthesizer must produce grounded answers
from real tool evidence.

### Status: ✅ Complete

### 2A — Capability Registry & Architecture

- [x] Design and implement `utils/capability_registry.py`
  - `Capability` dataclass: `name`, `category`, `description`, `input_schema`, `output_description`, `deterministic`, `independent`, `consumes_previous_results`, `node_name`
  - `REGISTRY: dict[str, Capability]` — single authoritative source for all registered capabilities
  - `get_planner_context() -> str` — generate capability list for planner system prompt
  - `get_node_map() -> dict[ToolName, str]` — generate router dispatch map from registry
- [x] Register all 4 Phase 1 capabilities in the registry
- [x] Update `utils/prompts.py::PLANNER_SYSTEM_PROMPT` to be generated from `get_planner_context()`
- [x] Update `agent/router.py::_TOOL_NODE_MAP` to be derived from `get_node_map()`
- [x] Add ADR-009 documenting the Capability Registry decision

### 2B — Planner Integration & Validation

- [x] Implement integration test script `tests/integration/test_planner_live.py` (skipped in CI, run manually with a real Gemini API key)
  - 15 representative queries covering all intent types
  - Assert each returns an `AnalysisPlan` with the correct `intent`
  - Assert each plan's `steps` have valid `parameters` matching the capability's `input_schema`
- [x] Iterate on `PLANNER_SYSTEM_PROMPT` until ≥13/15 queries produce correct plans
- [x] Validate that planner injects dataset schema summary (already wired, needs live verification)
- [x] Validate that `PlanStep.parameters` conform to `MetricsRequest`, `TrendsRequest`, etc. for all 4 Phase 1 tools
- [x] Add planner prompt unit tests: mock LLM returning known plans, assert router dispatches correctly
- [x] Migrate `GeminiLLM.chat()` from flat-prompt to `genai.ChatSession` for proper multi-turn context (remove the `TODO` in `gemini.py`)

### 2C — New Analytical Capabilities

For each new capability: implement the tool function, write the Pydantic request
schema, wire the LangGraph node, register in the Capability Registry, update
`graph.py`, and write a test module with at least 8 tests before marking complete.

#### `data_profile` capability

- [x] `DataProfileRequest` Pydantic schema (no required parameters)
- [x] `execute_data_profile()` — DuckDB queries for:
  - Row count and column count
  - Date range (`MIN(Date)`, `MAX(Date)`)
  - Numeric ranges: `MIN`, `MAX`, `MEAN`, `STDDEV` per metric column
  - Categorical cardinality: `COUNT(DISTINCT col)` per dimension column
  - Null counts per column
  - Data quality warnings: negative profit rows, duplicate rows, out-of-range dates
- [x] `data_profile_tool_node` — reads plan step, returns structured `ToolResult`
- [x] Register in Capability Registry as `DATA_ACCESS`, `independent=True`
- [x] Add `DATA_PROFILE` to `ToolName` enum in `models/schemas.py`
- [x] Wire node in `agent/graph.py`
- [x] `tests/test_data_profile.py` — 8+ tests

#### `compare` capability

- [x] `CompareRequest` Pydantic schema: `metric`, `aggregation`, `dimension`, `value_a`, `value_b`, optional `filters`
- [x] `execute_compare()` — two filtered aggregation queries + delta computation (absolute + percentage)
- [x] `compare_tool_node`
- [x] Register in Capability Registry as `CORE_ANALYSIS`, `independent=True`
- [x] Add `COMPARE` to `ToolName` enum
- [x] Wire node in `agent/graph.py`
- [x] `tests/test_compare.py` — 8+ tests covering region vs region, period vs period, category vs category, zero-division guard

#### `contribution` capability

- [x] `ContributionRequest` Pydantic schema: `metric`, `dimension`, optional `filters`, optional `limit`
- [x] `execute_contribution()` — `SUM(metric) OVER () AS grand_total` window function, percentage derivation
- [x] `contribution_tool_node`
- [x] Register in Capability Registry as `CORE_ANALYSIS`, `independent=True`
- [x] Add `CONTRIBUTION` to `ToolName` enum
- [x] Wire node in `agent/graph.py`
- [x] `tests/test_contribution.py` — 8+ tests: region contribution to revenue, category to profit, sum-to-100% invariant

#### `profitability` capability

- [x] `ProfitabilityRequest` Pydantic schema: `dimension`, optional `filters`, optional `limit`
- [x] `execute_profitability()` — `SUM(Profit) / NULLIF(SUM(Revenue), 0) AS profit_margin_pct` per group
- [x] Explicit guard: never treat `Revenue` as a proxy for profitability
- [x] `profitability_tool_node`
- [x] Register in Capability Registry as `CORE_ANALYSIS`, `independent=True`
- [x] Add `PROFITABILITY` to `ToolName` enum
- [x] Wire node in `agent/graph.py`
- [x] `tests/test_profitability.py` — 8+ tests: dimension grouping, margin computation, zero-revenue guard, ordering

#### `variance` capability

- [x] `VarianceRequest` Pydantic schema: `metric`, `granularity`, optional `group_by`, optional `filters`
- [x] `execute_variance()` — `LAG(metric) OVER (ORDER BY period)` window function with absolute and percentage delta
- [x] `variance_tool_node`
- [x] Register in Capability Registry as `CORE_ANALYSIS`; `independent=True`
- [x] Add `VARIANCE` to `ToolName` enum
- [x] Wire node in `agent/graph.py`
- [x] `tests/test_variance.py` — 8+ tests: monthly delta, null handling for first row, percentage change precision

### 2D — Synthesizer Integration & Grounding

- [x] Integration test `tests/integration/test_synthesizer_live.py` (manual, requires API key)
  - Feed real `ToolResult` objects from Phase 1 tools to synthesizer
  - Assert synthesizer does not introduce numbers absent from `ToolResult.data`
  - Test multi-tool scenarios: `[METRICS, CHARTS]`, `[TRENDS, COMPARE]`
- [x] Iterate on `SYNTHESIZER_SYSTEM_PROMPT` if hallucination is observed
- [x] Add evidence-citation pattern to synthesizer prompt: each claim should reference its step number

### 2E — End-to-End & Multi-turn Tests

- [x] `tests/integration/test_e2e.py` — full graph invocation with live Gemini key
  - At least 5 queries: metrics, trends, compare, contribution, mixed
  - Assert `final_answer` is non-empty
  - Assert `tool_results` contains ≥1 `ToolResult(success=True)`
  - Assert `errors` is empty
- [x] Multi-turn context test: Q1 sets up context, Q2 references "that" / "the West region"
- [x] Planner accuracy verification: ≥13/15 sample queries produce correct intent

### 2F — Phase 2 Documentation Updates

- [x] Update `docs/architecture.md`:
  - Mark all Phase 2 capabilities as implemented
  - Remove "Phase 2 Design Target" note from Capability Registry section
  - Update Mermaid diagram node list
- [x] Update `docs/development-plan.md`: mark Phase 2 tasks complete
- [x] Update `docs/decisions.md`: add ADR-009 (Capability Registry)
- [x] Update `README.md`: reflect Phase 2 capabilities as implemented

### Acceptance Criteria

- [x] `pytest tests/ -v` (offline) — all tests pass, count increases from 73
- [x] `pytest tests/integration/ -v` (requires `GEMINI_API_KEY`) — all integration tests pass
- [x] Planner accuracy: ≥13/15 representative queries produce correct `intent` and valid `PlanStep.parameters`
- [x] `data_profile` runs without error and returns all 10 fields
- [x] `compare` returns correct delta for North vs South revenue
- [x] `contribution` percentages sum to 100.0 (within floating-point tolerance)
- [x] `profitability` does not confuse revenue ranking with margin ranking
- [x] `variance` correctly returns `null` delta for first period row
- [x] Synthesizer answer for a single-step metrics query contains no numbers not in `ToolResult.data`
- [x] End-to-end test passes for: "What is revenue by region?" (metrics → synthesizer)

---

## Phase 3 — Product Experience & Advanced Analytics

**Objective**: Build the full Streamlit chat interface with visible plan trace and
chart rendering. Add advanced analytical capabilities for statistical investigation.

### Status: ✅ Complete

### 3A — Streamlit UI

- [x] Wrap `build_graph(llm)` and `load_dataset()` in `@st.cache_resource`
- [x] Initialise `st.session_state["messages"]` and `st.session_state["agent_state"]` at startup
- [x] Sidebar: dataset info card (row count, column list, date range) from `get_schema_description()`
- [x] Chat panel: render `st.session_state["messages"]` as alternating user/assistant bubbles
- [x] `st.chat_input` for new queries
- [x] On submit: call `graph.invoke(create_initial_state(query, history))`, display `final_answer`
- [x] Loading spinner (`st.spinner`) during graph execution
- [x] Persist `messages` list across reruns via `st.session_state`

### 3B — Execution Plan Trace Panel

- [x] Two-column layout: chat left, trace right
- [x] Render `plan.intent` and `plan.rationale` in the trace panel before tool execution display
- [x] Render each `PlanStep` as a numbered item: tool name, description, `depends_on`
- [x] Render each `ToolResult` with ✓/✗ indicator, step number, and row count or error message
- [x] Render `errors` in `st.error()` if non-empty
- [x] If `final_answer` starts with "I'm sorry", apply `st.warning()` styling

### 3C — Chart Rendering

- [x] After each invocation, check `chart_artifacts`
- [x] For each figure dict: `st.plotly_chart(go.Figure(fig_dict), use_container_width=True)`
- [x] Charts rendered below the assistant message or in the trace panel (decide based on layout testing)

### 3D — Advanced Capabilities

#### `anomaly_detection` capability

- [x] `AnomalyRequest` Pydantic schema: `metric`, `method` (`iqr` | `zscore`), optional `group_by`, optional `threshold`
- [x] `execute_anomaly_detection()`:
  - IQR: `PERCENTILE_CONT(0.25)`, `PERCENTILE_CONT(0.75)` → compute `IQR`, flag rows outside `[Q1 - 1.5×IQR, Q3 + 1.5×IQR]`
  - Z-score: `(value - AVG) / STDDEV`, flag where `|z| > threshold`
- [x] `anomaly_detection_tool_node`
- [x] Register in Capability Registry as `ADVANCED_ANALYSIS`
- [x] Add `ANOMALY_DETECTION` to `ToolName` enum
- [x] Wire node in `agent/graph.py`
- [x] `tests/test_anomaly_detection.py` — 8+ tests

#### `correlation` capability

- [x] `CorrelationRequest` Pydantic schema: `field_a`, `field_b`, optional `group_by`, optional `filters`
- [x] `execute_correlation()` — `CORR(field_a, field_b)` from DuckDB
- [x] Synthesizer prompt must include: "Correlation does not establish causation."
- [x] `correlation_tool_node`
- [x] Register in Capability Registry as `ADVANCED_ANALYSIS`
- [x] Add `CORRELATION` to `ToolName` enum
- [x] Wire node in `agent/graph.py`
- [x] `tests/test_correlation.py` — 8+ tests

#### `segmentation` capability

- [x] `SegmentationRequest` Pydantic schema: `metric`, `dimensions` (list of 2 columns), optional `filters`, optional `limit`
- [x] `execute_segmentation()` — multi-column `GROUP BY` (e.g. `Region, Category`)
- [x] `segmentation_tool_node`
- [x] Register in Capability Registry as `ADVANCED_ANALYSIS`
- [x] Add `SEGMENTATION` to `ToolName` enum
- [x] Wire node in `agent/graph.py`
- [x] `tests/test_segmentation.py` — 8+ tests

### 3E — Error & Edge Case Hardening

- [x] Empty query: returns user-facing error, not a stack trace
- [x] Query with no matching data: tool returns `[]`, synthesizer acknowledges it gracefully
- [x] Ambiguous query: planner sets `intent=UNKNOWN`, synthesizer asks for clarification
- [x] Malformed `AnalysisPlan` from LLM: `model_validate_json` raises → planner catches → `errors` → `error_handler`
- [x] `charts` with no prior data: `ToolResult(success=False, error=...)` rather than exception

### Acceptance Criteria

- [x] User can type a question and receive a text answer in the chat panel
- [x] Execution plan (intent + rationale + steps) appears in the trace panel
- [x] Charts render in the UI using `st.plotly_chart`
- [x] Conversation history persists across multiple questions in the same session
- [x] Page does not crash on invalid query — shows user-facing error
- [x] `anomaly_detection`, `correlation`, `segmentation` return correct results on canonical dataset
- [x] All new tests pass; total offline test count increases from Phase 2 total (136 tests passing)

---

## Phase 4 — Evaluation, Hardening & Deployment

**Objective**: Validate end-to-end quality, harden edge cases, and deploy to production.

### Status: ✅ Complete

### 4A — Evaluation Suite

- [x] Write 35 representative queries covering all capability types and edge cases
- [x] Record for each: intent classification accuracy, tool execution success, synthesizer quality
- [x] Target: ≥22/25 queries produce a correct, useful answer (Achieved 35/35 evaluation cases)
- [x] Fix identified failures via prompt iteration or tool fix
- [x] Extend `tests/` with regression tests for previously failed queries

### 4B — Numerical Correctness & Silent-Correctness Gates

- [x] For all DuckDB queries, write at least one test with manually verified expected values
- [x] Profit margin computation: verify `Profit / Revenue` does not divide by zero
- [x] Contribution percentages: verify they sum to 100.0
- [x] Variance deltas: verify first-row null and subsequent calculations match Excel manual check
- [x] Correlation coefficient: cross-check with `numpy.corrcoef` in tests
- [x] Citation integrity: strictly audit `[Step X]` citations to prevent hallucinated step references

### 4C — Code Quality & Security

- [x] All public functions have type hints and docstrings
- [x] No bare `except:` clauses
- [x] `pytest tests/ --ignore=tests/integration -v` passes 100% (212 passing tests)
- [x] `SensitiveDataFilter` redacts Google API keys, Bearer tokens, and secrets from logs and streams
- [x] No references to obsolete Superstore schema anywhere in the codebase or tests

### 4D — Performance & Telemetry

- [x] DuckDB query latency <50ms for single and multi-step tools on canonical dataset
- [x] Full graph invocation (excluding LLM API latency) <350ms
- [x] `@st.cache_resource` / `@st.cache_data` optimizes DuckDB session connection

### 4E — Documentation Reconciliation

- [x] `README.md` updated to reflect all completed phases and 13 actual capabilities
- [x] `docs/development-plan.md` all Phase 0–4 tasks marked complete
- [x] `docs/architecture.md` reconciled with current LangGraph StateGraph, Capability Registry, and Google GenAI SDK
- [x] `docs/decisions.md` ADRs 1–11 reconciled with current architecture

### 4F — Release Candidate Readiness

- [x] Bundled canonical dataset `data/Sales_Dataset_2024.xlsx` and verified reproducible Parquet generation
- [x] Streamlit workspace UI with independent scrolling panels and full telemetry inspector
- [x] Evaluation benchmark harness (`35/35` cases, 100% Intent, Tool, Parameter, and DuckDB Execution success)
- [x] Acceptance test suite runner (`25/25` cases passed, 100% success rate)

---

## Current Status Summary

| Phase | Description | Status |
|---|---|---|
| 0 | Project skeleton, contracts, test harness | ✅ Complete |
| 1 | Canonical dataset, DuckDB foundation, 4 deterministic tools, 73 tests | ✅ Complete |
| 2 | Capability Registry, Gemini planner integration, 5 new analytical capabilities, synthesizer grounding | ✅ Complete |
| 3 | Streamlit UI, plan trace, chart rendering, 3 advanced capabilities | ✅ Complete |
| 4 | Evaluation suite, numerical correctness, release hardening, documentation | ✅ Complete |

---

## Capability Implementation Roadmap (13 Deterministic Tools)

| Capability | Category | Phase | Status |
|---|---|---|---|
| `data_query` | DATA_ACCESS | 1 | ✅ Complete |
| `metrics` | CORE_ANALYSIS | 1 | ✅ Complete |
| `trends` | CORE_ANALYSIS | 1 | ✅ Complete |
| `charts` | PRESENTATION | 1 | ✅ Complete |
| `data_profile` | DATA_ACCESS | 2 | ✅ Complete |
| `data_clean` | DATA_ACCESS | 2 | ✅ Complete |
| `compare` | CORE_ANALYSIS | 2 | ✅ Complete |
| `contribution` | CORE_ANALYSIS | 2 | ✅ Complete |
| `profitability` | CORE_ANALYSIS | 2 | ✅ Complete |
| `variance` | CORE_ANALYSIS | 2 | ✅ Complete |
| `anomaly_detection` | ADVANCED | 3 | ✅ Complete |
| `correlation` | ADVANCED | 3 | ✅ Complete |
| `segmentation` | ADVANCED | 3 | ✅ Complete |

---

## Deferred (Phase 4 / Future)

The following capabilities are documented as design targets but are outside
the scope of Phases 2–3:

- **Hypothesis-driven investigation**: The agent proposes follow-up questions
  based on evidence found in the current turn.
- **Report / export**: Download query results as CSV, charts as PNG, or a full
  turn summary as a structured PDF.
- **Advanced statistical extensions**: Regression, forecasting (Prophet/ARIMA),
  cohort analysis.
- **Dynamic dataset switching**: Upload a new dataset at runtime; the planner
  re-adapts its capability list and parameter schemas to the new schema.
- **OpenAILLM / Anthropic provider**: Additional `BaseLLM` implementations
  behind the existing abstraction.

None of these require new infrastructure. They extend the existing architecture
without replacing it.
