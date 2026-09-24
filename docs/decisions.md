# Architecture Decision Records — Insight Copilot

Architecture Decision Records (ADRs) document the significant technical choices
made during design and implementation. Each record explains the context that
forced a decision, the options that were available, what was chosen, and the
consequences of that choice.

New ADRs are added whenever an important architectural decision is made.
Superseded records are updated with a reference to the replacing ADR rather
than deleted — history matters.

---

## ADR-001 — LangGraph as the Orchestration Layer

**Date**: 2026-09-21
**Status**: Accepted

### Context

The agent must execute a variable-length sequence of analytical tools in
a specific order determined at runtime by the planner. The sequence can be
one step long (a single metric query) or several steps long (data query →
trend analysis → chart). The routing between steps must be conditional —
the next node depends on the current state, not a fixed script.

Additionally, the execution trace (which tools ran, in what order, with what
results) must be surfaced in the UI. This requires the orchestration layer to
make the execution path explicit and inspectable.

### Decision

Use **LangGraph `StateGraph`** as the orchestration layer.

### Alternatives Considered

**LangChain `AgentExecutor` with tool-calling**
The executor hides the execution path inside a loop that the developer does
not directly control. Tools are selected by the LLM dynamically at runtime
rather than from an explicit pre-computed plan. This makes the trace hard to
extract and display, and it couples tool selection to the LLM at every step
rather than only at planning time. Rejected because it violates the requirement
for an inspectable, deterministic execution path.

**Plain LangChain sequential chains**
A `SequentialChain` or `RunnableSequence` cannot handle conditional branching
or variable-length sequences without external control logic. Adding that logic
manually would mean reimplementing what LangGraph already provides. Rejected
because it adds complexity without benefit.

**Custom orchestration loop (plain Python)**
A hand-written `while current_step < len(steps): run_tool(...)` loop would
work functionally but foregoes LangGraph's built-in features: typed state
management, reducer annotations, checkpoint support, and the ability to
visualise the graph. Also harder to test — LangGraph compiled graphs expose
`get_graph()` for node/edge inspection. Rejected as unnecessary reinvention.

### Consequences

- **Positive**: The execution path is declared as graph edges — fully auditable
  and testable. `test_graph.py` verifies the node set without making any API calls.
- **Positive**: LangGraph's `operator.add` reducers make multi-node state
  accumulation (appending `ToolResult` objects across tool steps) safe and
  explicit.
- **Positive**: The conditional edge pattern (`router_node` returning a string
  key) maps cleanly to the multi-step dispatch requirement.
- **Negative**: LangGraph is an additional dependency with its own API surface
  and release cadence. `langgraph>=0.2.0` is pinned in `requirements.txt`.
- **Negative**: LangGraph requires `TypedDict` for state — Pydantic `BaseModel`
  cannot be used directly as the state container (see ADR-002 for the separation
  of concerns this creates).

---

## ADR-002 — TypedDict for AgentState, Pydantic for Data Contracts

**Date**: 2026-09-21
**Status**: Accepted

### Context

LangGraph's `StateGraph` requires the graph state to be a `TypedDict` (or
a compatible mapping type). It uses `Annotated` field metadata to attach
reducer functions (`operator.add`) to specific fields. This mechanism is not
compatible with Pydantic `BaseModel`, which uses its own field annotation
system.

At the same time, the data objects that flow *through* the state (execution
plans, tool results, messages) benefit strongly from Pydantic's validation,
serialisation, and JSON schema generation — particularly for structured LLM
output parsing.

### Decision

- **`AgentState`** is a `TypedDict` with `total=False`. It is the LangGraph
  state container. Its fields reference Pydantic types but are not themselves
  Pydantic-validated.
- **All structured data contracts** (`AnalysisPlan`, `PlanStep`, `ToolResult`,
  `Message`) are Pydantic `BaseModel` subclasses defined in `models/schemas.py`.

### Alternatives Considered

**Using Pydantic for everything**
LangGraph does not support Pydantic `BaseModel` as the state type without
a compatibility shim, which adds fragility. Rejected to avoid fighting the
framework.

**Using plain dicts for data contracts**
Without Pydantic, the LLM's structured output (the `AnalysisPlan` JSON)
would need to be validated manually, and field types would not be enforced.
A malformed plan from the LLM would propagate undetected into the router.
Rejected because Pydantic's `model_validate_json` catches schema violations
at the boundary where LLM output enters the system.

### Consequences

- **Positive**: Clean separation — `TypedDict` for the LangGraph container,
  Pydantic for the data contracts inside it.
- **Positive**: `llm.structured_chat(messages, AnalysisPlan)` uses
  `AnalysisPlan.model_validate_json(raw_json)` to validate the LLM's JSON
  response before it enters the graph.
- **Positive**: Pydantic's `model_json_schema()` is used to inject the schema
  into the Gemini prompt, guiding the model toward valid output.
- **Negative**: Two different validation systems in the same codebase. The
  distinction (TypedDict vs BaseModel) must be understood by every contributor.
  Documented in this ADR and in `CONTRIBUTING.md`.

---

## ADR-003 — DuckDB for All Analytical Computation

**Date**: 2026-09-21
**Status**: Accepted

### Context

The agent needs to execute analytical queries — aggregations, rankings, window
functions, filters — against a tabular dataset. These queries must be
deterministic (same input → same output), auditable (readable by a human
reviewer), and fast (< 1 second for the canonical dataset size of 2,000 rows).

### Decision

Use **DuckDB** running in-process as the sole data computation engine.
All tool functions execute parameterised SQL against a DuckDB connection.
Pandas is used only for data transport (converting DuckDB results to
`list[dict]`), not for computation.

### Alternatives Considered

**Supabase / PostgreSQL**
A hosted database server introduces network latency, authentication, connection
pooling, and infrastructure management. For a single-file dataset of 2,000 rows
(Sales_Dataset_2024.xlsx → Parquet), this is disproportionate. Rejected — out of
scope and unnecessary complexity for the assignment.

**SQLite**
SQLite is designed for transactional (OLTP) workloads. It lacks native support
for `MEDIAN`, `PERCENTILE_CONT`, and most window functions that trend analysis
requires. It also does not read CSV or Parquet files natively. Rejected because
it does not cover the full analytical query surface.

**Pandas-only querying**
Pandas can perform aggregations and groupby operations, but:
1. The logic lives in Python method chains, which are harder to audit than SQL.
2. Complex analytical queries (rolling averages, period-over-period change)
   require verbose multi-step Pandas code compared to a single SQL window
   function.
3. Pandas holds entire DataFrames in memory; DuckDB operates on chunked data
   and uses vectorised execution, making it significantly faster on larger files.
Rejected because DuckDB SQL is more readable, more powerful, and faster for
the OLAP workload this project targets.

**SQLAlchemy with SQLite**
SQLAlchemy adds an ORM layer on top of SQLite without solving the analytical
function gap. Rejected for the same reasons as SQLite above.

### Consequences

- **Positive**: DuckDB reads Parquet and Excel natively. The project uses an
  Excel → Parquet pipeline (`ensure_parquet_dataset()`) so all queries target
  the Parquet file via a registered view — no repeated file-format conversion
  overhead at query time.
- **Positive**: SQL is explicit — every query can be read, reviewed, and
  logged independently.
- **Positive**: In-process — no server to start, no port to open, no
  authentication to manage.
- **Positive**: DuckDB supports `MEDIAN`, `PERCENTILE_CONT`, all standard
  window functions, and `PIVOT` natively.
- **Negative**: DuckDB is a single-writer, in-process database. It cannot
  serve multiple concurrent Streamlit sessions safely without care.
  Acceptable at assignment scope; a production deployment would need a
  per-session DuckDB connection strategy.

---

## ADR-004 — Streamlit as the UI Layer

**Date**: 2026-09-21
**Status**: Accepted

### Context

The application requires a chat interface, an execution-trace panel, and
Plotly chart rendering. The development timeline is constrained by the
internship assignment schedule. The engineering effort should be concentrated
on the agent and analytical layers, not on frontend development.

### Decision

Use **Streamlit** as the UI framework.

### Alternatives Considered

**Next.js / React with a FastAPI backend**
A React frontend communicating with a FastAPI backend would require:
- A separate process for the API server
- REST or WebSocket endpoints for streaming the agent response
- Frontend state management for the chat history
- Plotly.js integration on the frontend
- Significantly more code for the same user-facing functionality

Rejected. The engineering effort is not justified for an analytical chatbot
assignment where the focus is the agent architecture.

**Gradio**
Gradio is a viable alternative to Streamlit for ML demos. It offers slightly
less layout control and a different component model. Rejected in favour of
Streamlit because Streamlit has better support for multi-column layouts,
`st.plotly_chart` for native Plotly rendering, and more flexible session-state
management.

**Flask / Jinja2 templates**
Raw Flask would require building all UI components manually. Rejected for
the same reason as Next.js — frontend complexity is not the focus of this
assignment.

### Consequences

- **Positive**: Streamlit's `st.plotly_chart` renders Plotly `fig.to_dict()`
  outputs natively — no JavaScript required.
- **Positive**: `st.session_state` provides the persistence layer needed for
  multi-turn conversation history without a database.
- **Positive**: The entire application is a single Python process — no server
  split, no CORS, no API contracts to maintain between frontend and backend.
- **Positive**: Streamlit Community Cloud deploys directly from a GitHub
  repository with zero infrastructure configuration.
- **Negative**: Streamlit reruns the entire script on every user interaction.
  Expensive operations (dataset loading, graph compilation) must be wrapped in
  `@st.cache_resource` to avoid re-execution on every message.
- **Negative**: Streamlit's threading model limits true streaming of LangGraph
  node outputs. The agent will run to completion before the UI updates.

---

## ADR-005 — Gemini as the Initial LLM Provider

**Date**: 2026-09-21
**Status**: Accepted

### Context

The assignment specifies Gemini API as the initial LLM provider. The agent
requires two distinct LLM call patterns:
1. **Structured output** (planner): JSON response that parses directly into
   a Pydantic model.
2. **Free-form text** (synthesizer): Natural-language narrative answer.

### Decision

Use **Google Gemini** (`google-genai` SDK, configurable via `GEMINI_MODEL` env var;
production default: `gemini-3.5-flash`) as the primary LLM provider, accessed through an abstract
`BaseLLM` interface defined in `llm/base.py`. The concrete implementation
lives in `llm/gemini.py`. Provider selection is handled by `llm/factory.py`.

**Structured output implementation**: `GeminiLLM.structured_chat()` uses
`response_mime_type="application/json"` and appends the Pydantic model's
JSON schema to the prompt. The response is parsed with
`schema.model_validate_json(raw_json)`.

**Free-form implementation**: `GeminiLLM.chat()` flattens the message list
to a prompt string using `_messages_to_prompt()` and calls
`generate_content()` with `temperature=0.3`.

### Alternatives Considered

**OpenAI GPT-4o / GPT-4o-mini**
OpenAI's function-calling and `response_format={"type": "json_object"}` modes
are more mature and widely used. However, the assignment specifies Gemini.
The `BaseLLM` abstraction means an `OpenAILLM` implementation can be added
later without changing any agent code.

**Anthropic Claude**
Similar capability profile to GPT-4o. Same rationale: assignment specifies
Gemini; abstraction allows future addition.

**Local model (Ollama)**
Would eliminate API costs and latency variability. Not selected because
structured JSON output from smaller local models is less reliable, and the
assignment is scoped to Gemini.

### Consequences

- **Positive**: Assignment requirement satisfied.
- **Positive**: `BaseLLM` abstraction means all agent code (`planner.py`,
  `synthesizer.py`) is provider-agnostic. Switching providers requires only
  a new class in `llm/` and updating `factory.py`.
- **Positive**: `create_llm()` reads from the `LLM_PROVIDER` environment
  variable, so the provider can be changed without code changes.
- **Negative**: `GeminiLLM.chat()` currently flattens messages to a single
  prompt string rather than using `genai.ChatSession`. This means multi-turn
  history is re-sent in full on every call. A `TODO` comment in `gemini.py`
  marks this for Phase 2 improvement.
- **Negative**: Gemini API key must be provisioned per developer and per
  deployment environment. Key management is documented in `.env.example`
  and `CONTRIBUTING.md`.

---

## ADR-006 — Deterministic Tools for All Analytical Computation

**Date**: 2026-09-21
**Status**: Accepted

### Context

Analytical chatbots that allow the LLM to perform calculations have a
well-documented failure mode: the model fabricates plausible-sounding but
incorrect numbers. This is unacceptable for a data analysis tool where the
user's business decisions may depend on the output.

### Decision

All numerical calculations, aggregations, trend computations, and chart
rendering are performed by **deterministic Python code** (DuckDB queries,
Plotly renders). The LLM is prohibited from computing any dataset-derived
value. It only:

1. Classifies intent and selects tools (planner).
2. Narrates the results that tool nodes have already computed (synthesizer).

This boundary is enforced architecturally: tool nodes have no access to
any `BaseLLM` instance. The `BaseLLM` is injected only into the planner and
synthesizer via factory closures.

### Alternatives Considered

**Allow the LLM to compute directly (tool-free agent)**
The LLM receives the dataset and computes the answer in its context window.
Rejected categorically: LLMs hallucinate on numerical tasks, context windows
are bounded, and there is no way to independently verify the model's
arithmetic. An agent that invents numbers is worse than no agent.

**Code-generation agent (LLM writes and executes Python/SQL)**
The LLM generates SQL or Pandas code that is then executed by a safe
sandbox. This is a valid pattern (e.g., OpenAI's Code Interpreter) but
introduces significant complexity: sandboxing, injection prevention, error
recovery from generated code. Rejected as out of scope for the assignment
and more complex than necessary for a bounded analytical domain.

### Consequences

- **Positive**: Results are reproducible. The same query on the same dataset
  always returns the same numbers.
- **Positive**: Every computation can be traced to a specific SQL query logged
  by the tool node.
- **Positive**: The synthesizer's prompt explicitly states: *"Use ONLY the
  numbers from the tool results — do not invent any data."* This is a
  defence-in-depth measure at the LLM instruction level.
- **Negative**: The set of supported analytical operations is bounded by the
  tool implementations. A question that falls outside the four tool types
  cannot be answered correctly until a new tool is added.
- **Negative**: Tool parameters must eventually be extracted from `PlanStep`
  objects, which requires the planner to produce well-structured step
  descriptions. This is a Phase 2 engineering task.

---

## ADR-007 — Visible Execution Plan Instead of Hidden Chain-of-Thought

**Date**: 2026-09-21
**Status**: Accepted

### Context

LLM agents typically reason through a hidden internal monologue (chain-of-thought)
before producing an answer. This reasoning is opaque to the user and cannot be
audited. For an analytical tool used in a professional context, this opacity is
undesirable: the user needs to understand *what* the agent is doing and *why*,
not just trust the answer.

### Decision

The planner produces a **structured `AnalysisPlan`** object — not a scratchpad
or chain-of-thought — using Gemini's JSON mode. The `AnalysisPlan` contains:

- `intent`: classified intent enum value
- `rationale`: a maximum of 3 plain-English sentences explaining why this plan
  was chosen
- `steps`: an ordered list of `PlanStep` objects (tool + description)
- `selected_tools`: flat list of tool names

This plan is written to `AgentState` and is explicitly surfaced in the
Streamlit UI trace panel before tool execution begins.

The planner system prompt states: *"Do NOT include chain-of-thought. Only the
rationale field is exposed to users."*

### Alternatives Considered

**Expose raw chain-of-thought**
Verbose internal reasoning is confusing to non-technical users and often
contains hedging, backtracking, and irrelevant content. Rejected.

**No plan exposure (black-box agent)**
Hiding the plan entirely removes a key property of the system: inspectability.
If the agent gives a wrong answer, the user has no way to understand why.
Rejected.

**Expose only the final answer**
Removes the transparency advantage. If the agent runs a `METRICS` query when
the user intended a `TRENDS` analysis, the user would have no way to detect
the misclassification. Rejected.

### Consequences

- **Positive**: The plan is surfaced *before* execution, allowing the user to
  see what is about to happen and potentially stop it.
- **Positive**: The plan is the mechanism by which the agent explains itself —
  no separate explanation step is needed.
- **Positive**: The structured `AnalysisPlan` enables unit-testing of the
  planner independently of the tools (mock LLM returning a known plan, then
  assert that the router dispatches correctly).
- **Negative**: The planner must produce valid JSON that conforms to the
  `AnalysisPlan` schema. Prompt engineering effort is required to ensure
  reliability. `model_validate_json` will raise on non-conforming output,
  which the planner node catches and converts to an error state.

---

## ADR-008 — Centralised Prompts in `utils/prompts.py`

**Date**: 2026-09-21
**Status**: Accepted

### Context

System prompts are the primary interface through which developer intent is
communicated to the LLM. If they are scattered across node implementation
files, they are difficult to review, compare, and iterate on.

### Decision

All system prompts (`PLANNER_SYSTEM_PROMPT`, `SYNTHESIZER_SYSTEM_PROMPT`) live
as module-level string constants in `utils/prompts.py`. Node implementations
import them by name.

### Alternatives Considered

**Prompts inline in node files**
Harder to review in isolation. A reviewer who wants to audit all LLM
instructions must navigate multiple files. Rejected.

**Prompts in a YAML/JSON config file**
Adds a loading step and a file format to maintain. No meaningful advantage
over Python string constants at the current scale. Rejected.

**Prompts fetched from a prompt management service (LangSmith, Helicone)**
Disproportionate infrastructure for an assignment. Rejected.

### Consequences

- **Positive**: One file to open when reviewing or changing LLM instructions.
- **Positive**: Enables prompt versioning via git blame.
- **Positive**: Clear separation: node files contain orchestration logic,
  `prompts.py` contains LLM instructions.
- **Negative**: Importing from `utils.prompts` creates a dependency that must
  not create circular imports. Module dependency direction is documented in
  `CONTRIBUTING.md`: `models → llm → utils → tools → agent → app`.

---

## ADR-009 — Pre-Execution Plan Validation & Graph Robustness Boundary

**Date**: 2026-09-22
**Status**: Accepted

### Context

When the LLM planner produces a structured `AnalysisPlan`, invalid parameters, out-of-order step sequences, nonexistent tools, or cyclical/forward step dependencies could cause downstream runtime crashes during tool execution. Relying on tools to fail individually at runtime creates noisy errors, leaks internal exceptions to the user, and wastes compute cycles.

### Decision

Implement a centralized pre-execution validation boundary (`agent/validator.py`) executing before the LangGraph router dispatches any step.
The validator strictly enforces:
1. Contiguous 1..N step numbering with zero duplicates.
2. Tool registration within the authoritative `Capability Registry`.
3. Parameter conformance against each tool's Pydantic `request_schema`.
4. Dependency DAG acyclicity (`dep < step_number`, no self-dependencies, no forward references).
5. Router error redirection: Invalid plans bypass tool dispatch and route directly to a structured `_error_handler_node`.

### Consequences

- **Positive**: 100% parameter validity guaranteed before entering tool execution loops.
- **Positive**: Malformed LLM outputs receive clean, actionable user diagnostic guidance rather than unhandled Python exceptions.
- **Positive**: Simplifies individual tool implementations, as parameter contracts are validated before dispatch.

---

## ADR-010 — Modern `google-genai` SDK Migration & Structured Latency Telemetry

**Date**: 2026-09-22
**Status**: Accepted

### Context

The legacy `google-generativeai` package has reached end-of-support and produces deprecated `FutureWarning` alerts during execution. Furthermore, tracking turn latency and millisecond-level execution bottlenecks (Planner LLM vs DuckDB Tool SQL vs Synthesizer LLM) is essential for production operational visibility.

### Decision

1. Migrate `llm/gemini.py` to the modern Google GenAI SDK (`google-genai` library), utilizing native `response_schema` support with Pydantic models and elimination of all deprecation warnings.
2. Implement structured telemetry logging across `AgentState`:
   - Every graph invocation turn generates a unique `run_id` (UUID4).
   - Planner LLM duration, individual tool execution durations, synthesizer duration, and total turn latency are logged and surfaced in the Streamlit UI trace panel.

### Consequences

- **Positive**: Zero deprecation warnings in test suite and runtime logs.
- **Positive**: Full operational telemetry across every analytical turn.
- **Positive**: Future-proof compatibility with current and future Google Gemini models (`google-genai` SDK).

---

## ADR-011 — Two-Tier Bronze/Silver Data Layer & Dimension Hygiene Isolation

**Date**: 2026-09-23
**Status**: Accepted

### Context

Enterprise users frequently request data cleaning, typo standardization (e.g. `Easst` $\to$ `East`, `MOBLIE` $\to$ `Mobile`), and missing value imputation. If mutations are applied directly to the canonical source file or global in-memory tables, raw data integrity is compromised, and resetting or comparing before-and-after distributions becomes impossible.

### Decision

Implement an explicit two-tier Medallion architecture within DuckDB and session memory:
1. **Bronze (`raw_dataset`)**: Immutable view created directly from the canonical source file (`data/Sales_Dataset_2024.xlsx`). Never modified by cleaning operations.
2. **Silver (`dataset`)**: Active working view utilized by analytical tools (`metrics`, `trends`, `profitability`, `compare`, `charts`). Mutations performed by `data_clean` operate exclusively on this view.
3. **Session Reset (`reset_to_raw_dataset()`)**: Re-clones the Silver view from Bronze instantaneously whenever requested by the user or benchmark runners.

### Consequences

- **Positive**: Strict data lineage preservation — raw source data is never permanently corrupted.
- **Positive**: Enables comparative before/after auditing across multi-turn cleaning conversations.
- **Positive**: Seamless deterministic reset between test cases in automated test runners.

---

## ADR-012 — Provider-Agnostic LLM Architecture & Transparent Groq Fallback

**Date**: 2026-09-24
**Status**: Accepted

### Context

Transient provider availability failures (rate limits `429 RESOURCE_EXHAUSTED`, service errors `503 SERVICE_UNAVAILABLE`, network/transport errors) on primary LLM endpoints can interrupt analytical turns during active user sessions or evaluation benchmarks. Duplicating retry logic inside individual nodes (`planner.py` or `synthesizer.py`) violates node single-responsibility and creates brittle code paths.

### Decision

1. Keep all agent nodes (`planner`, `synthesizer`) strictly provider-agnostic by consuming the abstract `BaseLLM` interface.
2. Implement `FallbackLLM` in `llm/fallback.py` as a transparent wrapper over a primary (`GeminiLLM`, production: `gemini-3.5-flash`) and an optional secondary (`GroqLLM` using `openai/gpt-oss-120b`) provider.
3. `FallbackLLM` invokes `_is_availability_error(exc)` on any exception from the primary. Recognized availability/transport failures (rate limits `429`, service errors `500/502/503/504`, connection/timeout errors) transparently route to the fallback. Authentication, validation, and application errors are **not** caught by fallback — they are re-raised to the caller as normal exceptions.

### Consequences

- **Positive**: Transient Gemini availability or transport failures can trigger transparent fallback to the configured Groq provider, reducing visible disruption during rate-limited sessions.
- **Positive**: Authentication errors, bad request parameters, and application bugs are not silently swallowed — they propagate normally, making them discoverable.
- **Positive**: Complete abstraction — planner and synthesizer nodes remain 100% agnostic of provider failover logic.
- **Positive**: Comprehensive unit test coverage verifying fallback triggers and non-trigger cases (`tests/test_fallback_llm.py`).
- **Negative**: Fallback is not a zero-downtime guarantee. If both primary and fallback providers are unavailable or misconfigured, the turn will still fail. If `GROQ_API_KEY` is absent, fallback itself will fail.

