# Architecture Decision Records — Insight Copilot

Each decision is recorded here with its context, the options considered,
the chosen option, and the rationale.

---

## ADR-001 — LangGraph over bare LangChain

**Date**: 2026-09-21  
**Status**: Accepted

### Context
The agent must support multi-step execution (e.g., data_query → trends → charts)
with conditional routing between steps.  A linear LangChain chain cannot handle
variable-length, conditionally-branching execution paths.

### Options considered
1. LangChain `AgentExecutor` with tool-calling
2. LangGraph `StateGraph`
3. Custom orchestration loop (plain Python)

### Decision
LangGraph `StateGraph`.

### Rationale
- Explicit node + edge declaration makes the execution flow auditable and testable.
- `StateGraph` natively supports conditional routing and typed shared state.
- LangGraph's graph structure maps naturally to the planner → router → tool(s) → synthesizer flow.
- Option 1 hides the execution path in the executor; we need it visible for the UI trace.
- Option 3 would require re-implementing checkpointing, error propagation, and streaming.

---

## ADR-002 — TypedDict for AgentState (not Pydantic BaseModel)

**Date**: 2026-09-21  
**Status**: Accepted

### Context
LangGraph requires the graph state to be a `TypedDict` (or a class that
implements the same protocol).  Pydantic `BaseModel` is not directly
compatible with LangGraph's state management and reducer annotations.

### Decision
Use `TypedDict` with `Annotated` fields for reducer specification.

### Rationale
- LangGraph's `operator.add` reducer pattern uses `Annotated[list[X], operator.add]`
  on `TypedDict` fields — not a Pydantic mechanism.
- Pydantic is used for *data contracts* (schemas.py) that flow *through* the state,
  not for the state container itself.

---

## ADR-003 — DuckDB for all analytical computation

**Date**: 2026-09-21  
**Status**: Accepted

### Context
The agent must compute aggregations, trends, and rankings from a tabular dataset.
These calculations must be deterministic and must not involve the LLM.

### Options considered
1. Pandas in-memory operations
2. DuckDB in-process SQL
3. SQLite

### Decision
DuckDB.

### Rationale
- DuckDB is optimised for analytical (OLAP) queries on columnar data.
- SQL is explicit and auditable — easier to review for correctness than Pandas chains.
- DuckDB reads CSV, Parquet, and Excel directly without a separate load step.
- No server process required (in-process like SQLite but with OLAP semantics).
- Pandas is used for data transport (list of dicts) but not for computation.

---

## ADR-004 — Gemini as initial LLM provider

**Date**: 2026-09-21  
**Status**: Accepted

### Context
The assignment specifies Gemini API as the initial LLM provider.

### Decision
Implement `GeminiLLM` as the first provider; abstract behind `BaseLLM` and `create_llm()`.

### Rationale
- Assignment requirement.
- The `BaseLLM` abstraction means switching to another provider later requires only
  a new implementation class — no agent code changes.
- `gemini-2.0-flash` offers a good balance of capability and cost for development.

---

## ADR-005 — Structured output for planner, free-form for synthesizer

**Date**: 2026-09-21  
**Status**: Accepted

### Context
Two nodes call the LLM with different output requirements:
- The **planner** must produce a machine-readable `AnalysisPlan`.
- The **synthesizer** must produce a human-readable narrative.

### Decision
- Planner: `structured_chat()` with JSON mode + Pydantic schema validation.
- Synthesizer: `chat()` with free-form text output.

### Rationale
- Forcing the synthesizer to return JSON and then rendering it would add unnecessary
  complexity with no benefit.
- Forcing the planner to return free-form text would require fragile string parsing.
- Pydantic validation on the planner output immediately catches malformed plans.

---

## ADR-006 — No hidden chain-of-thought

**Date**: 2026-09-21  
**Status**: Accepted

### Context
LLM reasoning steps ("let me think…") are often useful internally but can be
misleading or verbose when exposed to users.

### Decision
The `AnalysisPlan.rationale` field is limited to ≤3 sentences of plain English.
No scratchpad, no intermediate reasoning, no chain-of-thought is stored or exposed.

### Rationale
- The UI will surface the structured plan to users; they need clarity, not a
  transcript of the model's reasoning process.
- Keeping the rationale short and structured makes it easy to display inline.
- Chain-of-thought can be re-enabled internally (e.g., via a hidden system message)
  in a future phase if quality requires it, without changing the public interface.

---

## ADR-007 — Centralised prompts in utils/prompts.py

**Date**: 2026-09-21  
**Status**: Accepted

### Context
Prompts evolve frequently during development.  If they are scattered across
node files they become hard to review and iterate on.

### Decision
All system prompts live in `utils/prompts.py` as module-level string constants.

### Rationale
- Single place to audit LLM instructions.
- Easier to A/B test prompt variants.
- Nodes stay focused on orchestration logic, not prompt text.
