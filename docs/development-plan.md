# Development Plan — Insight Copilot

This is a **living engineering document**. Update it whenever implementation
progresses. A task is marked complete only when the implementation satisfies
its acceptance criteria and any associated tests pass. The existence of a file
does not mean its implementation is complete.

---

## Phase 0 — Project Skeleton and Contracts

**Objective**: Establish the repository structure, typed interfaces, and test
harness before any live API or data calls are made. Define what every
component will do before implementing any of it.

### Tasks

- [x] Repository initialised and pushed to GitHub
- [x] `.gitignore` with secrets, venvs, DuckDB files, and dataset files excluded
- [x] `.gitattributes` enforcing LF line endings
- [x] `CONTRIBUTING.md` — branching strategy, commit conventions, coding standards
- [x] `requirements.txt` with all production and development dependencies
- [x] `.env.example` — template for all environment variables
- [x] Virtual environment (`.venv`) with all dependencies installed
- [x] `models/schemas.py` — Pydantic contracts: `Intent`, `ToolName`, `AnalysisPlan`, `PlanStep`, `ToolResult`, `Message`, `Role`
- [x] `agent/state.py` — `AgentState` TypedDict with `operator.add` reducers on list fields
- [x] `llm/base.py` — `BaseLLM` abstract interface with `chat()` and `structured_chat()`
- [x] `llm/gemini.py` — `GeminiLLM` skeleton: JSON mode for structured output, flat-prompt for chat
- [x] `llm/factory.py` — `create_llm()` factory with `LLMProvider` enum
- [x] `agent/planner.py` — planner node skeleton with error handling and history truncation
- [x] `agent/router.py` — `router_node` conditional edge + `advance_step` node
- [x] `agent/synthesizer.py` — synthesizer node skeleton with fallback behaviour
- [x] `agent/graph.py` — full `StateGraph` wiring: 9 nodes, static edges, conditional routing edge
- [x] `tools/data_query.py` — stub node + `run_data_query()` interface defined
- [x] `tools/metrics.py` — stub node + `compute_metric()` + `AggregationType` enum
- [x] `tools/trends.py` — stub node + `compute_trend()` + `TrendType` enum
- [x] `tools/charts.py` — stub node + `render_chart()` + `ChartType` enum
- [x] `utils/prompts.py` — `PLANNER_SYSTEM_PROMPT` and `SYNTHESIZER_SYSTEM_PROMPT`
- [x] `utils/data_loader.py` — `load_dataset()`, `get_schema()`, `get_connection()` interfaces defined
- [x] `app.py` — Streamlit shell: page config, sidebar, two-column layout (chat + trace)
- [x] `.streamlit/config.toml` — dark theme configuration
- [x] `conftest.py` — project root on `sys.path` for pytest
- [x] `pytest.ini` — test discovery configuration
- [x] `tests/test_graph.py` — graph construction tests (mock LLM, assert node set)
- [x] `tests/test_router.py` — router logic and step-advance tests (10 cases)
- [x] `tests/test_tools.py` — tool node stubs and interface tests (15 cases)
- [x] `docs/architecture.md` — field-level state docs, node IO tables, routing algorithm, data flow trace
- [x] `docs/decisions.md` — 8 ADRs
- [x] `docs/development-plan.md` — this document
- [x] `README.md` — professional engineering documentation with Mermaid diagram

### Acceptance Criteria

- [x] `pytest tests/ -v` passes with 27 tests, 0 failures, no live API calls required
- [x] Graph compiles and contains all 9 expected nodes (verified by `test_graph.py`)
- [x] Router dispatches correctly for all tool types and edge cases (verified by `test_router.py`)
- [x] All tool stubs return `ToolResult` with correct `tool` and `step_number` (verified by `test_tools.py`)
- [x] No API keys or secrets in any committed file
- [x] All public functions and classes have type hints and docstrings

### Status: ✅ Complete

---

## Phase 1 — Data Layer and Tool Implementation

**Objective**: Connect a real dataset to DuckDB and implement all four analytical
tool functions so that the graph can execute a complete turn (excluding LLM
integration) with real computed results.

### Tasks

**Data layer**

- [ ] Decide on dataset file format (CSV confirmed: Superstore `orders.csv`)
- [ ] Implement `utils/data_loader.py::get_connection()` — create in-process DuckDB connection, cache it at module level
- [ ] Implement `utils/data_loader.py::load_dataset()` — read file, register as DuckDB view named `dataset`
- [ ] Implement `utils/data_loader.py::get_schema()` — query `DESCRIBE dataset` and return `list[dict[str, str]]`
- [ ] Add column-name normalisation (lowercase, strip spaces) at load time
- [ ] Add date-column parsing (`Order Date`, `Ship Date`) as `DATE` type

**Data query tool**

- [ ] Implement `tools/data_query.py::run_data_query()` — parameterised DuckDB `SELECT` with column selection, equality filters, and row limit
- [ ] Wire `data_query_tool_node` to extract parameters from `plan.steps[current_step]` and call `run_data_query()`
- [ ] Return `ToolResult(success=True, data=rows)` on success
- [ ] Return `ToolResult(success=False, error=str(exc))` on DuckDB exception

**Metrics tool**

- [ ] Implement `tools/metrics.py::compute_metric()` — DuckDB `GROUP BY` with `AggregationType` dispatch
- [ ] Support `TOP N` via `ORDER BY metric DESC LIMIT N`
- [ ] Wire `metrics_tool_node` to extract parameters from plan step
- [ ] Return `ToolResult(success=True, data=rows)` / `(success=False, error=...)` appropriately

**Trends tool**

- [ ] Implement `tools/trends.py::compute_trend()` — DuckDB window functions for `TIME_SERIES`, `ROLLING_AVERAGE`, `PERIOD_OVER_PERIOD`, `CUMULATIVE`
- [ ] Wire `trends_tool_node` to extract parameters from plan step
- [ ] Return appropriate `ToolResult`

**Charts tool**

- [ ] Implement `tools/charts.py::render_chart()` — Plotly `go.Figure` construction for `ChartType` dispatch
- [ ] Serialise output as `fig.to_dict()` stored in `ToolResult.data`
- [ ] Wire `charts_tool_node` to find most recent successful `ToolResult` in state, pass its `data` to `render_chart()`
- [ ] Write rendered figure to `chart_artifacts` in state

**PlanStep parameter extraction (shared across tools)**

- [ ] Define how parameters are passed from `PlanStep.description` to tool functions — either:
  - Parse free-text `description` (fragile), OR
  - Add structured `parameters: dict` field to `PlanStep` schema (preferred)
- [ ] Update planner prompt to include parameter structure in the plan
- [ ] Update all tool nodes to read parameters from `PlanStep.parameters`

### Acceptance Criteria

- [ ] `load_dataset("data/superstore.csv")` completes without error and registers `dataset` view in DuckDB
- [ ] `run_data_query("dataset", filters={"Category": "Technology"}, limit=10)` returns 10 rows of Technology orders
- [ ] `compute_metric("dataset", "Sales", AggregationType.SUM, group_by=["Region"])` returns 4 rows with correct structure
- [ ] `compute_trend("dataset", "Sales", "Order Date", TrendType.TIME_SERIES)` returns monthly series
- [ ] `render_chart(rows, ChartType.BAR, x_column="Region", y_column="Sales", title="Sales by Region")` returns a non-empty Plotly dict
- [ ] All tool nodes return `ToolResult(success=True)` when called with a valid plan step
- [ ] New integration tests in `tests/test_data_layer.py` pass using in-memory DuckDB with 20 synthetic rows
- [ ] New integration tests in `tests/test_tools_integration.py` pass using the same in-memory DuckDB

### Tests to Write

- [ ] `tests/test_data_layer.py` — `load_dataset`, `get_schema`, `get_connection` with a temp CSV file
- [ ] `tests/test_tools_integration.py` — each tool function with in-memory DuckDB synthetic data

### Status: 🔲 Not Started

---

## Phase 2 — LLM Integration and Planner Validation

**Objective**: Validate that the planner produces correct `AnalysisPlan` objects
on real queries, and that the synthesizer produces coherent answers from real
tool results. Requires a live Gemini API key.

### Tasks

**Planner integration**

- [ ] Write an integration test script (not in the main pytest suite) that:
  - Loads `.env` and initialises `GeminiLLM`
  - Sends 15 sample queries (covering all 5 intent types)
  - Asserts that the returned `AnalysisPlan` has the expected `intent` and at least one valid `step`
- [ ] Iterate on `PLANNER_SYSTEM_PROMPT` until ≥ 13/15 queries produce correct plans
- [ ] Inject dataset schema (`get_schema()` output) into the planner prompt
- [ ] Add `PlanStep.parameters` support if not done in Phase 1 (see Phase 1 parameter extraction task)

**GeminiLLM multi-turn improvement**

- [ ] Migrate `GeminiLLM.chat()` from flat prompt string to `genai.ChatSession` for proper multi-turn context
- [ ] Remove the `TODO` comment in `gemini.py` when complete

**Synthesizer integration**

- [ ] Write an integration test that feeds real `ToolResult` objects (from Phase 1 tools) to the synthesizer
- [ ] Verify the synthesizer does not invent numbers not present in the `ToolResult.data`
- [ ] Iterate on `SYNTHESIZER_SYSTEM_PROMPT` if hallucination is observed

**End-to-end smoke test**

- [ ] Write a single end-to-end test: `build_graph(llm).invoke({"query": "What is total sales by region?", "messages": []})` and assert:
  - `final_answer` is a non-empty string
  - `tool_results` contains at least one `ToolResult(success=True)`
  - `errors` is empty

### Acceptance Criteria

- [ ] 13/15 sample planning queries produce an `AnalysisPlan` with the correct `intent`
- [ ] End-to-end smoke test passes with a live Gemini API key
- [ ] Synthesizer answer for a single-step metrics query does not contain any numbers absent from the `ToolResult.data`
- [ ] `GeminiLLM.chat()` uses `ChatSession` for conversation history

### Tests to Write

- [ ] `tests/integration/test_planner_live.py` — live API (skipped in CI, run manually)
- [ ] `tests/integration/test_e2e.py` — full graph invocation (live API, skipped in CI)

### Status: 🔲 Not Started

---

## Phase 3 — Streamlit UI

**Objective**: Build the full Streamlit chat interface with execution-plan trace,
chart rendering, and session-state management.

### Tasks

**Session state**

- [ ] Initialise `st.session_state["messages"]` as empty list at startup
- [ ] Initialise `st.session_state["agent_state"]` to persist `AgentState` across reruns
- [ ] Wrap `build_graph(llm)` and `load_dataset()` in `@st.cache_resource` to prevent re-execution on reruns

**Dataset loading**

- [ ] Sidebar: file uploader (`st.file_uploader`) accepting CSV, Parquet, Excel
- [ ] On upload: call `load_dataset(uploaded_file)`, show column schema in sidebar
- [ ] Fallback: read `DATASET_PATH` env var if no file is uploaded

**Chat panel**

- [ ] Render `st.session_state["messages"]` as alternating user/assistant chat bubbles
- [ ] `st.chat_input` for new queries
- [ ] On submit: call `graph.invoke({"query": query, "messages": session_messages})`
- [ ] Display `final_answer` as new assistant message
- [ ] Loading spinner during graph execution

**Execution trace panel**

- [ ] After each invocation, render `plan.intent` and `plan.rationale`
- [ ] Render each `PlanStep` as a numbered item with tool name and description
- [ ] Render each `ToolResult` with success/failure indicator and step number
- [ ] Render `errors` in an `st.error()` box if non-empty

**Chart rendering**

- [ ] After each invocation, check `chart_artifacts`
- [ ] For each figure dict: `st.plotly_chart(go.Figure(fig_dict), use_container_width=True)`

**Error display**

- [ ] If `errors` is non-empty, show `st.error()` with all error messages
- [ ] If `final_answer` starts with "I'm sorry", style as warning

### Acceptance Criteria

- [ ] User can upload a CSV, type a question, and receive a text answer in the chat panel
- [ ] Execution plan (intent + rationale + steps) appears in the trace panel
- [ ] Charts generated by the chart tool render in the chat or trace panel
- [ ] Conversation history persists across multiple questions in the same session
- [ ] Page does not crash on an invalid query — shows a user-facing error message

### Tests to Write

- [ ] Manual verification checklist (no automated UI tests at this stage)

### Status: 🔲 Not Started

---

## Phase 4 — Evaluation and Polish

**Objective**: Validate end-to-end quality across a broad set of queries, harden
edge cases, and prepare the project for submission and demonstration.

### Tasks

**Query evaluation**

- [ ] Write 25 representative queries covering all intent types and edge cases
- [ ] Run each through the full graph and record: plan accuracy, tool execution success, synthesizer quality
- [ ] Target: ≥ 22/25 queries produce a correct, useful answer
- [ ] Fix identified failure cases via prompt iteration or tool fix

**Edge case hardening**

- [ ] Empty query: returns a meaningful error message (not a stack trace)
- [ ] Query with no matching data: tool returns empty `[]`, synthesizer acknowledges it
- [ ] Ambiguous query: planner sets `intent=UNKNOWN`, returns a clarification request
- [ ] Malformed `AnalysisPlan` from LLM: `model_validate_json` raises, planner catches, routes to error_handler

**Performance**

- [ ] DuckDB query latency < 500ms for any tool on the Superstore dataset
- [ ] Full graph invocation (excluding LLM API latency) < 1s

**Code quality**

- [ ] All modules ≤ 200 lines
- [ ] All public functions have type hints and docstrings
- [ ] No bare `except:` clauses
- [ ] `ruff check .` passes with zero warnings (add ruff to dev dependencies)

**Documentation**

- [ ] `README.md` updated to reflect completed status
- [ ] `docs/development-plan.md` all Phase 1–3 tasks marked complete
- [ ] `docs/architecture.md` updated to remove "stub" labels from implemented tools

**Deployment**

- [ ] Push to `main` and connect to Streamlit Community Cloud
- [ ] Configure `GEMINI_API_KEY` via Streamlit Cloud secrets panel
- [ ] Verify the deployed app loads and can answer a test query

### Acceptance Criteria

- [ ] ≥ 22/25 evaluation queries produce a correct answer
- [ ] All 27 existing tests still pass
- [ ] DuckDB queries complete in < 500ms
- [ ] Deployed to Streamlit Community Cloud and accessible via public URL

### Tests to Write

- [ ] Extend `tests/` with regression cases from the evaluation queries that previously failed

### Status: 🔲 Not Started

---

## Current Status

| Phase | Description | Status |
|---|---|---|
| 0 | Skeleton and contracts | ✅ Complete |
| 1 | Data layer and tool implementation | 🔲 Not started |
| 2 | LLM integration and planner validation | 🔲 Not started |
| 3 | Streamlit UI | 🔲 Not started |
| 4 | Evaluation and polish | 🔲 Not started |

---

## Completed

- Phase 0: all skeleton tasks, 27 tests passing, documentation written

---

## In Progress

*(nothing currently in progress)*

---

## Next

**Immediate next task**: Begin Phase 1 — Data Layer.

Priority order:
1. `utils/data_loader.py` — implement `get_connection()` and `load_dataset()`
2. `tools/data_query.py` — implement `run_data_query()` and wire tool node
3. Add `PlanStep.parameters` to the schema (prerequisite for all other tools)
4. `tools/metrics.py` — implement `compute_metric()` and wire tool node
5. `tools/trends.py` — implement `compute_trend()` and wire tool node
6. `tools/charts.py` — implement `render_chart()` and wire tool node
7. Integration tests for data layer and tools

---

## Blocked

*(nothing currently blocked)*

---

## Known Issues

| Issue | Severity | Phase to address |
|---|---|---|
| `GeminiLLM.chat()` flattens message history to a single string rather than using `ChatSession` | Medium — multi-turn context is partially lost | Phase 2 |
| `PlanStep.depends_on` field is defined in the schema but not enforced by the router | Low — all current plans are sequential | Phase 1 or 2 |
| Tool nodes do not yet extract parameters from `PlanStep` — they return stubs | Critical — tools cannot compute without parameters | Phase 1 |
| Streamlit UI is not connected to the agent | Critical — app is not functional end-to-end | Phase 3 |
| History truncation is hard-coded at 10 messages | Low — sufficient for the assignment scope | Phase 4 if needed |
