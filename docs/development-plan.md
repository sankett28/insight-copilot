# Development Plan — Insight Copilot

This is a **living engineering document** for **Insight Copilot**. A task is marked complete only when the implementation satisfies its acceptance criteria and any associated tests pass.

---

## Canonical Dataset & Data Architecture

- **Canonical Source File**: `data/Sales_Dataset_2024.xlsx` (2,000 rows, 10 columns)
- **Runtime Representation**: `data/sales_dataset.parquet` (automatically converted on first startup)
- **Execution Engine**: DuckDB in-process OLAP engine over Parquet (`CREATE VIEW dataset AS SELECT * FROM read_parquet(...)`)

### Canonical Dataset Schema (10 Fields)

1. `Date` (TIMESTAMP) — Temporal date field (2024-01-01 to 2024-12-31)
2. `Region` (VARCHAR) — Categorical dimension (`North`, `South`, `East`, `West`)
3. `Product` (VARCHAR) — Categorical dimension (`Smartwatch`, `Monitor`, `Mobile`, `Laptop`, etc.)
4. `Salesperson` (VARCHAR) — Categorical dimension (`Alice`, `Bob`, `Charlie`, `David`, `Eva`, etc.)
5. `Units_Sold` (DOUBLE) — Numeric metric
6. `Unit_Price` (DOUBLE) — Numeric metric
7. `Category` (VARCHAR) — Categorical dimension (`Accessories`, `Office`, `Electronics`)
8. `Revenue` (DOUBLE) — Numeric metric
9. `Cost` (DOUBLE) — Numeric metric
10. `Profit` (DOUBLE) — Numeric metric

---

## Current Status Table

| Phase | Description | Status |
|---|---|---|
| **Phase 0** | Architecture & Contracts | **Complete** |
| **Phase 1** | Deterministic Data Layer & Tools | **Complete** |
| **Phase 2** | LLM Planning & End-to-End Agent | **In Progress** |
| **Phase 3** | Streamlit Product Experience | **In Progress** |
| **Phase 4** | Evaluation, Hardening & Deployment | **Not Started** |

---

## Phase 0 — Architecture & Contracts

**Objective**: Establish the repository structure, typed interfaces, LangGraph state machine, and test harness before any live API calls.

### Tasks & Verification

- [x] Repository initialised with branch controls and `.gitignore` excluding secrets and venvs.
- [x] `CONTRIBUTING.md` enforcing commit conventions, logical branching, and PR workflows.
- [x] `requirements.txt` with core stack: `langgraph`, `langchain-core`, `google-generativeai`, `pydantic>=2.7`, `duckdb>=1.0`, `pandas>=2.2`, `plotly>=5.22`, `streamlit>=1.36`, `pytest`.
- [x] `models/schemas.py`: Pydantic data contracts (`Intent`, `ToolName`, `AnalysisPlan`, `PlanStep`, `ToolResult`, `Message`, `Role`, `MetricsRequest`, `TrendsRequest`, `DataQueryRequest`, `ChartRequest`, `DatasetSchema`).
- [x] `agent/state.py`: `AgentState` TypedDict with explicit separation of persistent conversation state (`messages`) vs per-turn state (`query`, `plan`, `selected_tools`, `current_step`, `tool_results`, `chart_artifacts`, `final_answer`, `errors`). Added `create_initial_state`.
- [x] `llm/base.py`, `llm/gemini.py`, `llm/factory.py`: `BaseLLM` interface and `GeminiLLM` factory.
- [x] `agent/planner.py`: Planner node skeleton with Gemini JSON mode output parsing.
- [x] `agent/router.py`: Deterministic `router_node` conditional edge and `advance_step` node.
- [x] `agent/synthesizer.py`: Synthesizer node skeleton with narrative synthesis and error fallback.
- [x] `agent/graph.py`: LangGraph `StateGraph` compilation with 9 nodes and static/conditional edges.
- [x] `docs/architecture.md`, `docs/decisions.md`: Architecture diagrams, field-level state docs, node IO contracts, and 8 ADRs.

### Status: ✅ Complete

---

## Phase 1 — Deterministic Data Layer & Tools

**Objective**: Connect the canonical `Sales_Dataset_2024.xlsx` dataset to a reliable DuckDB runtime and prove that all four analytical tools produce deterministic, validated results independently of the LLM and Streamlit UI.

### Five Functional Areas

#### A. Dataset & Runtime Layer (`utils/data_loader.py`)
- [x] Verify `Sales_Dataset_2024.xlsx` exists in `data/`.
- [x] Implement automatic Excel-to-Parquet conversion (`ensure_parquet_dataset`), generating `data/sales_dataset.parquet`.
- [x] Implement `get_dataset_path()` resolving paths relative to `PROJECT_ROOT`.
- [x] Verify `Date` column parsing as `TIMESTAMP` datetime.
- [x] Validate exact row count (2,000 rows) and 10 canonical columns via `validate_dataset()`.
- [x] Implement `get_connection()` for thread-safe DuckDB in-process connection with view `dataset`.
- [x] Implement `get_schema()` and `get_schema_description()` returning structured prompt summary metadata.

#### B. Data Query Tool (`tools/data_query.py`)
- [x] Implement `execute_data_query_request(req: DataQueryRequest)` selecting known columns.
- [x] Support filtering (`filters: dict[str, Any]`), sorting (`sort_by`, `sort_order`), and row limit (capped at 100 max).
- [x] Reject invalid/unknown columns cleanly and construct safe DuckDB SELECT queries without LLM SQL interpolation.
- [x] Return structured `ToolResult(success=True, data=rows)` or `ToolResult(success=False, error=str(exc))`.

#### C. Metrics Tool (`tools/metrics.py`)
- [x] Support canonical numeric fields: `Units_Sold`, `Unit_Price`, `Revenue`, `Cost`, `Profit`.
- [x] Support aggregations: `sum`, `average`/`avg`, `count`, `min`, `max`, `median`.
- [x] Support `group_by`, `filters`, `sort` direction, and `limit`.
- [x] Generate safe SQL from validated `MetricsRequest` parameters and execute via DuckDB.

#### D. Trends Tool (`tools/trends.py`)
- [x] Use `Date` as canonical temporal field.
- [x] Support time granularities: `day`, `week`, `month`, `quarter`, `year` using DuckDB `DATE_TRUNC`.
- [x] Support target numeric metric, optional `group_by` dimension, and `filters`.
- [x] Format ISO period strings cleanly (`YYYY-MM-DD`).

#### E. Charts Tool (`tools/charts.py`)
- [x] Support Plotly chart types: `bar`, `line`, `scatter`.
- [x] Consume preceding deterministic tool results from `state["tool_results"]` (or step specified in `depends_on`).
- [x] Return `fig.to_dict()` in `ToolResult.data` and `state["chart_artifacts"]`.
- [x] Ensure charts do not independently query the dataset.

---

### Phase 1 Test Harness

All tests run **100% offline**, without Streamlit, and without requiring a live Gemini API key:

- **Data Layer (`tests/test_data_loader.py`)**:
  - `test_dataset_path_resolution`: Verifies Parquet path resolution and existence.
  - `test_validate_canonical_dataset`: Validates 2,000 rows, 10 columns, and schema types.
  - `test_duckdb_schema_types`: Verifies DuckDB dataset view column types.
  - `test_schema_description_summary`: Verifies prompt summary formatting.
  - `test_missing_excel_file_raises`: Verifies controlled error if Excel file is missing.

- **Analytical Tools (`tests/test_tools.py`)**:
  - `test_metrics_total_revenue`: Computes total revenue sum ($20.7M+).
  - `test_metrics_revenue_by_category`: Validates grouping by Category (`Accessories`, `Office`, `Electronics`).
  - `test_metrics_profit_by_region`: Validates grouping by Region with limits.
  - `test_metrics_invalid_column`: Verifies Pydantic rejection of unknown metric columns (`Customer`).
  - `test_metrics_invalid_group_by`: Verifies rejection of unknown `group_by` columns.
  - `test_metrics_tool_node_execution`: Integration test for `metrics_tool_node`.
  - `test_trends_monthly_revenue`: Computes 12 monthly revenue data points for 2024.
  - `test_trends_monthly_profit`: Computes monthly profit trend.
  - `test_trends_with_filter_and_grouping`: Computes monthly trend filtered by Region and grouped by Category.
  - `test_trends_invalid_date_column`: Verifies rejection of invalid date columns.
  - `test_trends_tool_node_execution`: Integration test for `trends_tool_node`.
  - `test_data_query_filtered`: Tests raw row filtering by Region.
  - `test_data_query_limit_cap`: Verifies row limit enforcement.
  - `test_charts_rendering_bar`, `test_charts_rendering_scatter_and_line`: Verifies Plotly figure generation.
  - `test_charts_tool_node_multi_step`: Multi-step test where charts consumes preceding trends output.
  - `test_charts_missing_preceding_data`: Verifies controlled failure when no tabular data exists.
  - `test_tool_node_malformed_plan_step`: Verifies controlled `ToolResult(success=False)` on invalid parameters.

- **Router Node (`tests/test_router.py`)**:
  - `test_router_single_step`: Validates single-tool step dispatching.
  - `test_router_multi_step_dependency_success`: Validates step routing when dependencies succeed.
  - `test_router_dependency_failed_routes_to_error`: Redirects to `error_handler` if a dependent step failed.
  - `test_router_all_steps_complete_routes_to_synthesizer`: Routes to `synthesizer` upon step completion.
  - `test_advance_step`: Increments `current_step`.

- **State & Graph (`tests/test_graph.py`)**:
  - `test_graph_single_tool_execution`: Full MockLLM single-step execution pipeline.
  - `test_graph_multi_tool_execution`: Full MockLLM multi-step execution pipeline (trends -> charts).
  - `test_state_isolation_between_turns`: Verifies `create_initial_state` state isolation.

---

### Phase 1 Exit Criteria Checklist

1. [x] DuckDB reliably accesses `data/sales_dataset.parquet` generated from `Sales_Dataset_2024.xlsx`.
2. [x] Schema validation passes (2,000 rows, 10 canonical columns).
3. [x] `data_query` tool works deterministically.
4. [x] `metrics` tool works deterministically.
5. [x] `trends` tool works deterministically.
6. [x] `charts` tool works deterministically.
7. [x] Tool nodes correctly consume structured `PlanStep.parameters`.
8. [x] Invalid parameters produce controlled `ToolResult(success=False, error=...)` failures without crashing the graph.
9. [x] 31/31 unit tests pass offline without Gemini API keys.
10. [x] No Streamlit dependency required for tool test execution.
11. [x] Implementation matches canonical `Sales_Dataset_2024.xlsx` schema.
12. [x] Technical documentation (`docs/architecture.md`, `docs/decisions.md`) matches codebase.

### Status: ✅ Complete

---

## Phase 2 — LLM Planning & End-to-End Agent

**Objective**: Connect the deterministic execution engine to Gemini for live query intent classification, structured `AnalysisPlan` creation, and natural language answer synthesis.

### Tasks

- [ ] Refine `PLANNER_SYSTEM_PROMPT` to enforce structured parameter output matching `MetricsRequest`, `TrendsRequest`, `DataQueryRequest`, and `ChartRequest`.
- [ ] Verify `GeminiLLM.structured_chat` reliably parses structured `AnalysisPlan` outputs.
- [ ] Implement live API integration test suite evaluating Gemini planner across 20 representative query types.
- [ ] Verify Synthesizer prompt (`SYNTHESIZER_SYSTEM_PROMPT`) prevents numerical hallucination and uses only verified `ToolResult` data.
- [ ] Verify multi-turn context retention across sequential questions in `AgentState`.
- [ ] Implement malformed planner JSON recovery in `planner_node`.

### Status: 🔄 In Progress

---

## Phase 3 — Streamlit Product Experience

**Objective**: Provide a clean, analyst-focused web UI exposing conversation history, visible execution plans, tool trace logs, and Plotly charts.

### Tasks

- [x] Streamlit layout in `app.py` with dual-column layout (Chat vs. Plan & Tool Trace).
- [x] Automatic dataset discovery and sidebar schema metadata rendering.
- [x] Session state management (`st.session_state.messages`, `current_plan`, `current_tool_results`, `current_charts`).
- [x] Render visible execution plan (intent, rationale, step parameters).
- [x] Render tool trace expandable cards with row tables and JSON outputs.
- [x] Embed Plotly charts directly into conversation stream.
- [ ] Refine multi-turn conversation UI styling and error alert banners.

### Status: 🔄 In Progress

---

## Phase 4 — Evaluation, Hardening & Deployment

**Objective**: Hardening, 25-query benchmark evaluation, production packaging, and public deployment.

### Tasks

- [ ] Benchmark 25 representative evaluation queries (single-tool, multi-tool, multi-turn, edge cases).
- [ ] Measure numerical accuracy, plan correctness, and response latency.
- [ ] Package repository for Streamlit Community Cloud deployment with Streamlit Secrets (`GEMINI_API_KEY`).
- [ ] Verify public URL accessibility in Incognito browser mode.

### Status: 🔲 Not Started

---

## Current Next Step

**Single Most Important Engineering Action Remaining**:
Refine the `PLANNER_SYSTEM_PROMPT` and run a live Gemini API test script (`tests/integration/test_planner_live.py`) to verify that Gemini produces valid `PlanStep.parameters` for all 4 tool schemas (`metrics`, `trends`, `data_query`, `charts`) on complex analytical questions.
