# Development Plan — Insight Copilot

## Phase 0 — Skeleton & Contracts ✅ (current)

**Goal**: Establish the project structure, typed interfaces, and test harness
before any live API or data calls are made.

### Deliverables
- [x] `AgentState` TypedDict with annotated reducers
- [x] Pydantic schemas (`Intent`, `ToolName`, `AnalysisPlan`, `ToolResult`, `Message`)
- [x] `BaseLLM` abstract interface + `GeminiLLM` implementation skeleton
- [x] `LLMFactory` with provider enum
- [x] LangGraph `StateGraph` wired with all nodes and conditional routing
- [x] Planner, Router, Synthesizer node skeletons
- [x] Tool node stubs (data_query, metrics, trends, charts)
- [x] Tool interface functions defined (not yet implemented)
- [x] Centralised prompt strings (`utils/prompts.py`)
- [x] `data_loader` interface defined
- [x] Basic test suite (graph construction, router logic, tool stubs)
- [x] Documentation (architecture, development plan, decisions)
- [x] Streamlit shell with layout

---

## Phase 1 — Data Layer & Tool Implementation

**Goal**: Connect a real dataset to DuckDB and implement all four tools.

### Tasks
- [ ] Confirm dataset (format, columns, size)
- [ ] Implement `utils/data_loader.py` — DuckDB in-process connection, CSV/Parquet/Excel ingestion
- [ ] Implement `tools/data_query.py::run_data_query` — parameterised SELECT via DuckDB
- [ ] Implement `tools/metrics.py::compute_metric` — GROUP BY aggregations, TOP N rankings
- [ ] Implement `tools/trends.py::compute_trend` — time series, rolling avg, period-over-period
- [ ] Implement `tools/charts.py::render_chart` — Plotly bar, line, scatter, pie
- [ ] Update tool nodes to extract parameters from `plan.steps`
- [ ] Expand test suite with real DuckDB queries (using in-memory test data)
- [ ] Add dataset schema inspection to `data_loader.get_schema()`

---

## Phase 2 — LLM Integration & Planner

**Goal**: Make the planner produce valid `AnalysisPlan` objects from real queries.

### Tasks
- [ ] Set up `.env` with `GEMINI_API_KEY`
- [ ] Implement `GeminiLLM.chat()` and `GeminiLLM.structured_chat()` fully
  (multi-turn history, token limits, retry logic)
- [ ] Refine `PLANNER_SYSTEM_PROMPT` with dataset schema context
- [ ] Add schema injection: `data_loader.get_schema()` → planner context
- [ ] Integration test: planner produces valid plans for 10 sample queries
- [ ] Add plan parameter extraction: `PlanStep` should carry tool-specific parameters
  (e.g., which columns to query, which aggregation to compute)

---

## Phase 3 — Streamlit UI

**Goal**: Build the full chat interface with plan trace and chart rendering.

### Tasks
- [ ] Dataset upload widget in sidebar (or path input)
- [ ] Multi-turn chat panel with message history
- [ ] Execution plan / tool trace panel (shows `AnalysisPlan` + `ToolResult` per step)
- [ ] Chart rendering (Plotly figures from `chart_artifacts`)
- [ ] Session state management (`st.session_state` for `AgentState` persistence)
- [ ] Error display and graceful degradation
- [ ] Loading spinners / progress indicators during agent execution

---

## Phase 4 — Polish & Evaluation

**Goal**: Evaluate quality, harden edge cases, and prepare for demonstration.

### Tasks
- [ ] End-to-end test suite with synthetic dataset
- [ ] Evaluate 20+ sample queries across all intent types
- [ ] Prompt refinement based on evaluation results
- [ ] Edge case handling: empty results, unsupported questions, ambiguous queries
- [ ] Performance: ensure DuckDB queries complete in < 1 second for typical datasets
- [ ] README walkthrough with screenshots
- [ ] Final code review and cleanup
