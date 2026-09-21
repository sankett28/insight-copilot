# Architecture — Insight Copilot

> **Accuracy note**: This document describes the architecture as it is implemented
> in the repository at the time of writing. Unimplemented functionality is labelled
> explicitly. See [`docs/development-plan.md`](development-plan.md) for current status.

---

## System Overview

Insight Copilot is structured as a pipeline of explicitly separated concerns:

| Component | File(s) | Responsibility |
|---|---|---|
| **Streamlit UI** | `app.py` | Entry point. Renders the chat panel and execution-trace panel. Accepts user input and displays the final answer and chart artefacts. *(Shell only — not yet connected to agent.)* |
| **LangGraph StateGraph** | `agent/graph.py` | Wires all nodes, static edges, and the single conditional routing edge into a compiled, executable graph. |
| **AgentState** | `agent/state.py` | `TypedDict` that carries all data through the graph. Every node reads from and writes to this shared object. |
| **Planner** | `agent/planner.py` | LLM node. Classifies intent and produces a structured `AnalysisPlan` via Gemini's JSON mode. |
| **Router** | `agent/router.py` | Pure-Python conditional edge function. Reads `selected_tools[current_step]` and returns the next node name string. No LLM call. |
| **`advance_step`** | `agent/router.py` | Lightweight node. Increments `current_step` by 1 after each tool completes, enabling the multi-step loop. |
| **Tool nodes** | `tools/` | Deterministic execution nodes. Each appends a `ToolResult` to state. No LLM calls. *(Stub implementations — see Phase 1.)* |
| **DuckDB** | `utils/data_loader.py` | In-process OLAP engine. All analytical queries run here. *(Interface defined; implementation pending.)* |
| **Synthesizer** | `agent/synthesizer.py` | LLM node. Receives serialised `ToolResult` objects, calls Gemini with free-form chat, returns the plain-English answer. |
| **LLM Provider** | `llm/` | `BaseLLM` abstract interface + `GeminiLLM` implementation. Factory in `llm/factory.py`. |
| **Schemas** | `models/schemas.py` | Pydantic contracts: `AnalysisPlan`, `PlanStep`, `ToolResult`, `Message`, enums. |
| **Prompts** | `utils/prompts.py` | Centralised system prompts for planner and synthesizer. |

---

## Architecture Diagram

The diagram below reflects the actual compiled LangGraph graph as defined in
[`agent/graph.py`](../agent/graph.py).

```mermaid
flowchart TD
    U([User]) -->|query string| ST[Streamlit UI\napp.py]
    ST -->|AgentState| START([START])

    START --> PL[planner\nagent/planner.py]
    PL -->|intent, plan,\nselected_tools, current_step=0| RT[router\nagent/router.py]

    RT -->|errors present| EH[error_handler]
    RT -->|no tools selected OR\ncurrent_step >= len| SY[synthesizer\nagent/synthesizer.py]
    RT -->|selected_tools[current_step]| DQ[data_query\ntools/data_query.py]
    RT --> MT[metrics\ntools/metrics.py]
    RT --> TR[trends\ntools/trends.py]
    RT --> CH[charts\ntools/charts.py]

    DQ & MT & TR & CH -->|ToolResult appended| SA[step_advance\nagent/router.py]
    SA -->|current_step + 1| RT

    DQ & MT & TR -->|SQL| DB[(DuckDB\nutils/data_loader.py)]
    DB -->|rows as list of dicts| DQ & MT & TR

    SY -->|final_answer,\nassistant Message| END_([END])
    EH -->|final_answer with error| END_

    subgraph LLM["Gemini (google-generativeai)"]
        PL_LLM[structured_chat\nJSON mode → AnalysisPlan]
        SY_LLM[chat\ntemperature=0.3]
    end

    PL -.->|messages list| PL_LLM
    SY -.->|messages list| SY_LLM
```

---

## LangGraph State

`AgentState` is defined in [`agent/state.py`](../agent/state.py) as a
`TypedDict` with `total=False` (all keys optional). LangGraph uses it as the
single shared memory object that every node reads from and writes to.

Fields with `Annotated[list[X], operator.add]` use a **reducer**: LangGraph
merges node return values by *appending* to the existing list rather than
replacing it. All other fields use **last-write-wins**.

### Field Reference

---

#### `messages`

```python
messages: Annotated[list[Message], operator.add]
```

| | |
|---|---|
| **Type** | `list[Message]` (Pydantic model: `role: Role`, `content: str`, `metadata: dict`) |
| **Reducer** | `operator.add` — each node appends; no node can overwrite history |
| **Purpose** | Full conversation history across all turns. The planner reads the last 10 entries for context. |
| **Written by** | Synthesizer (appends one `Message(role=ASSISTANT, content=final_answer)` per turn) |
| **Read by** | Planner (last-10 slice for multi-turn context) |

---

#### `query`

```python
query: str
```

| | |
|---|---|
| **Type** | `str` |
| **Reducer** | Last-write-wins |
| **Purpose** | The raw natural-language question for the current turn. Reset each time the user submits a new query. |
| **Written by** | Application layer (before graph invocation) |
| **Read by** | Planner, Synthesizer |

---

#### `intent`

```python
intent: str
```

| | |
|---|---|
| **Type** | `str` (mirrors `Intent` enum value: `"data_query"`, `"metrics"`, `"trend"`, `"chart"`, `"combined"`, `"unknown"`) |
| **Reducer** | Last-write-wins |
| **Purpose** | Classified analytical intent. Written as a plain string so it can be displayed directly in the UI trace panel. |
| **Written by** | Planner |
| **Read by** | UI (trace display — not yet connected) |

---

#### `plan`

```python
plan: AnalysisPlan | None
```

| | |
|---|---|
| **Type** | `AnalysisPlan` (Pydantic: `intent`, `rationale`, `steps: list[PlanStep]`, `selected_tools`) or `None` |
| **Reducer** | Last-write-wins |
| **Purpose** | The structured execution plan produced by the planner. `None` until the planner runs, or if planning fails. |
| **Written by** | Planner |
| **Read by** | Synthesizer (passes `plan.rationale` and step list into the synthesis prompt); UI (trace display) |

---

#### `selected_tools`

```python
selected_tools: list[ToolName]
```

| | |
|---|---|
| **Type** | `list[ToolName]` (enum: `DATA_QUERY`, `METRICS`, `TRENDS`, `CHARTS`) |
| **Reducer** | Last-write-wins |
| **Purpose** | Ordered list of tools to run this turn. Derived directly from `plan.selected_tools`. The Router indexes into this list using `current_step`. |
| **Written by** | Planner |
| **Read by** | Router |

---

#### `current_step`

```python
current_step: int
```

| | |
|---|---|
| **Type** | `int` |
| **Reducer** | Last-write-wins |
| **Purpose** | Zero-based index into `selected_tools`. Tracks which tool to dispatch to next. Reset to `0` by the Planner at the start of each turn. |
| **Written by** | Planner (resets to `0`), `advance_step` node (increments by `1`) |
| **Read by** | Router |

---

#### `tool_results`

```python
tool_results: Annotated[list[ToolResult], operator.add]
```

| | |
|---|---|
| **Type** | `list[ToolResult]` (Pydantic: `tool`, `step_number`, `success: bool`, `data: Any`, `error: str \| None`) |
| **Reducer** | `operator.add` — each tool appends its result; earlier results are never overwritten |
| **Purpose** | Accumulated outputs from every tool execution in this turn. The Synthesizer uses this to compose the final answer. |
| **Written by** | Each tool node (appends one `ToolResult` per invocation) |
| **Read by** | Synthesizer, Charts tool (reads prior data results to render) |

---

#### `chart_artifacts`

```python
chart_artifacts: list[dict[str, Any]]
```

| | |
|---|---|
| **Type** | `list[dict]` — each dict is a Plotly figure serialised via `fig.to_dict()` |
| **Reducer** | Last-write-wins |
| **Purpose** | Plotly figures separated from the text answer so the UI can render them independently. |
| **Written by** | Charts tool *(not yet implemented)* |
| **Read by** | Streamlit UI *(not yet connected)* |

---

#### `final_answer`

```python
final_answer: str | None
```

| | |
|---|---|
| **Type** | `str` or `None` |
| **Reducer** | Last-write-wins |
| **Purpose** | The complete analyst-style response to the user's query. Set by the Synthesizer on success, or by `error_handler_node` on failure. `None` until the graph reaches one of those two nodes. |
| **Written by** | Synthesizer, `error_handler_node` |
| **Read by** | Streamlit UI |

---

#### `errors`

```python
errors: Annotated[list[str], operator.add]
```

| | |
|---|---|
| **Type** | `list[str]` |
| **Reducer** | `operator.add` — errors from different nodes accumulate |
| **Purpose** | Collects error messages from any node that encountered a problem. The Router checks `errors` first on every evaluation; a non-empty list causes an immediate redirect to `error_handler`. |
| **Written by** | Planner (on empty query or LLM exception), any tool node (on failure) |
| **Read by** | Router (checked before routing logic), Synthesizer (checked before LLM call) |

---

## Graph Nodes

### `planner`

**File**: [`agent/planner.py`](../agent/planner.py) — built via `build_planner_node(llm)` closure.

| | |
|---|---|
| **Responsibility** | Classify the user's intent and produce a structured `AnalysisPlan`. The only LLM call in the planning phase. |
| **Reads from state** | `query`, `messages` |
| **Writes to state** | `intent`, `plan`, `selected_tools`, `current_step` (reset to `0`) |
| **LLM call** | `llm.structured_chat(messages, AnalysisPlan)` — Gemini JSON mode, temperature `0.0` |
| **On empty query** | Returns `intent=UNKNOWN`, `plan=None`, `selected_tools=[]`, appends to `errors` |
| **On LLM exception** | Logs exception, returns same failure state as empty query |
| **Next node (static edge)** | Always `router` |

**Context window**: Passes system prompt + last 10 `messages` + current `query`. History truncation is hard-coded at 10 turns in `_build_planner_messages`.

---

### `router` (node body)

**File**: [`agent/router.py`](../agent/router.py) — `_passthrough_node` registered as node body.

| | |
|---|---|
| **Responsibility** | No-op. The actual routing logic lives in the `router_node` conditional-edge function attached to this node's outgoing edge. |
| **Reads from state** | Nothing |
| **Writes to state** | Nothing (`{}` returned) |
| **Next node** | Determined by the `router_node` conditional edge (see [Conditional Routing](#conditional-routing)) |

---

### `router_node` (conditional edge function)

**File**: [`agent/router.py`](../agent/router.py) — `router_node(state) -> str`.

This is not a node — it is a function called by LangGraph's conditional edge mechanism after the `router` node executes. It returns a **string key** that LangGraph maps to the next node.

| Priority | Condition | Returns |
|---|---|---|
| 1 | `len(errors) > 0` | `"error_handler"` |
| 2 | `len(selected_tools) == 0` | `"synthesizer"` |
| 3 | `current_step >= len(selected_tools)` | `"synthesizer"` |
| 4 | `selected_tools[current_step]` is a known `ToolName` | node name string from `_TOOL_NODE_MAP` |
| 5 | `selected_tools[current_step]` is unknown | `"error_handler"` |

---

### `step_advance`

**File**: [`agent/router.py`](../agent/router.py) — `advance_step(state) -> dict`.

| | |
|---|---|
| **Responsibility** | Increment `current_step` by 1 so the router advances to the next tool on its next evaluation. |
| **Reads from state** | `current_step` |
| **Writes to state** | `current_step` (incremented by 1) |
| **Possible errors** | None |
| **Next node (static edge)** | Always `router` |

---

### `data_query`

**File**: [`tools/data_query.py`](../tools/data_query.py)

| | |
|---|---|
| **Responsibility** | Execute a filtered SELECT against the dataset and return rows. |
| **Reads from state** | `plan`, `current_step` |
| **Writes to state** | `tool_results` (appends one `ToolResult`) |
| **Implementation status** | ⚠️ Stub — returns `ToolResult(success=False, error="not yet implemented")` |
| **Next node (static edge)** | Always `step_advance` |

---

### `metrics`

**File**: [`tools/metrics.py`](../tools/metrics.py)

| | |
|---|---|
| **Responsibility** | Compute aggregated metrics (SUM, AVG, COUNT, MIN, MAX, MEDIAN) via DuckDB GROUP BY. |
| **Reads from state** | `plan`, `current_step` |
| **Writes to state** | `tool_results` (appends one `ToolResult`) |
| **Implementation status** | ⚠️ Stub — returns `ToolResult(success=False, error="not yet implemented")` |
| **Next node (static edge)** | Always `step_advance` |

---

### `trends`

**File**: [`tools/trends.py`](../tools/trends.py)

| | |
|---|---|
| **Responsibility** | Analyse a measure over time using DuckDB window functions (time series, rolling average, period-over-period change, cumulative sum). |
| **Reads from state** | `plan`, `current_step` |
| **Writes to state** | `tool_results` (appends one `ToolResult`) |
| **Implementation status** | ⚠️ Stub — returns `ToolResult(success=False, error="not yet implemented")` |
| **Next node (static edge)** | Always `step_advance` |

---

### `charts`

**File**: [`tools/charts.py`](../tools/charts.py)

| | |
|---|---|
| **Responsibility** | Render a Plotly figure (bar, line, scatter, pie, area, heatmap) from a prior `ToolResult`'s data. Does not query DuckDB. |
| **Reads from state** | `tool_results` (to find the most recent successful result), `plan`, `current_step` |
| **Writes to state** | `tool_results` (appends figure `ToolResult`), `chart_artifacts` |
| **Implementation status** | ⚠️ Stub — returns `ToolResult(success=False, error="not yet implemented")` |
| **Next node (static edge)** | Always `step_advance` |

---

### `synthesizer`

**File**: [`agent/synthesizer.py`](../agent/synthesizer.py) — built via `build_synthesizer_node(llm)` closure.

| | |
|---|---|
| **Responsibility** | Narrate `tool_results` into a plain-English analyst-style answer. |
| **Reads from state** | `query`, `plan`, `tool_results`, `errors` |
| **Writes to state** | `final_answer`, `messages` (appends assistant `Message`) |
| **LLM call** | `llm.chat(messages, temperature=0.3)` — free-form text |
| **On errors with no results** | Bypasses LLM; returns a safe error-acknowledgment string |
| **On LLM exception** | Returns a fallback message without re-raising |
| **Next node (static edge)** | `END` |

**Prompt composition**: `SYNTHESIZER_SYSTEM_PROMPT` + a user message containing: `query`, `plan.rationale`, `plan.steps`, and each `ToolResult` formatted as `[Step N | tool_name] ✓/✗\n<json data>`.

---

### `error_handler`

**File**: [`agent/graph.py`](../agent/graph.py) — `_error_handler_node`.

| | |
|---|---|
| **Responsibility** | Terminal node for unrecoverable errors. Logs all accumulated errors. Writes a user-facing error string to `final_answer` if one is not already set. |
| **Reads from state** | `errors`, `final_answer` |
| **Writes to state** | `final_answer` (only if not already set) |
| **Next node (static edge)** | `END` |

---

## Conditional Routing

The single conditional edge in the graph is attached to the `router` node and calls `router_node(state) -> str`.

### Decision Algorithm

```python
# Pseudocode from agent/router.py::router_node

if state["errors"]:                             # (1) any error → abort
    return "error_handler"

tools = state["selected_tools"]
step  = state["current_step"]

if not tools or step >= len(tools):             # (2) all steps done
    return "synthesizer"

tool = tools[step]                              # (3) dispatch next tool
return _TOOL_NODE_MAP.get(tool, "error_handler")
```

### `_TOOL_NODE_MAP`

```python
_TOOL_NODE_MAP = {
    ToolName.DATA_QUERY: "data_query",
    ToolName.METRICS:    "metrics",
    ToolName.TRENDS:     "trends",
    ToolName.CHARTS:     "charts",
}
```

### Routing Examples

**Single-tool query**: *"What is total revenue by region?"*

```
Plan: selected_tools = [METRICS]

router (step=0): METRICS → "metrics"
metrics → step_advance (step becomes 1)
router (step=1): 1 >= 1 → "synthesizer"
synthesizer → END
```

**Multi-tool query**: *"Show me a trend chart of monthly Technology sales."*

```
Plan: selected_tools = [TRENDS, CHARTS]

router (step=0): TRENDS → "trends"
trends → step_advance (step becomes 1)
router (step=1): CHARTS → "charts"
charts → step_advance (step becomes 2)
router (step=2): 2 >= 2 → "synthesizer"
synthesizer → END
```

**Error at planning**: *empty query submitted*

```
Plan: Planner writes errors=["Planner received an empty query."]

router (step=0): errors non-empty → "error_handler"
error_handler → END
```

---

## Tool Architecture

There is a hard boundary between LLM reasoning and deterministic execution:

```
┌─────────────────────────────────────────────────────────┐
│                  LLM RESPONSIBILITY                      │
│                                                          │
│  • Natural-language understanding                        │
│  • Intent classification                                 │
│  • Deciding which tools to run and in what order         │
│  • Narrating the results of tool execution               │
│                                                          │
│  Implemented in: planner.py, synthesizer.py             │
│  Temperature: 0.0 (planner), 0.3 (synthesizer)          │
└─────────────────────────────────────────────────────────┘
                           │
                    AnalysisPlan
                    (structured JSON)
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              DETERMINISTIC RESPONSIBILITY                │
│                                                          │
│  • All SQL queries (parameterised, no interpolation)     │
│  • All aggregations (SUM, AVG, COUNT, etc.)             │
│  • All window functions (rolling avg, period-over-period)│
│  • All chart rendering (Plotly)                          │
│                                                          │
│  Implemented in: tools/, utils/data_loader.py, DuckDB   │
│  No LLM access within tool nodes                         │
└─────────────────────────────────────────────────────────┘
```

**Enforcement**: Tool nodes receive only `AgentState` as input. They have no
reference to any `BaseLLM` instance. They cannot call the LLM even by mistake.
The `BaseLLM` is injected only into `build_planner_node` and `build_synthesizer_node`
via closure.

---

## Data Flow

Full trace of: *"What are the top 5 products by profit?"*

```
1. User types query into Streamlit UI
   ↓
2. app.py passes query to build_graph(llm).invoke({"query": query, "messages": []})
   ↓
3. [planner node]
   Reads: query="What are the top 5 products by profit?"
   Calls: llm.structured_chat([system_prompt, user_msg], AnalysisPlan)
   Gemini returns JSON → parsed to:
     AnalysisPlan(
       intent=METRICS,
       rationale="Ranking products by profit requires a single aggregation.",
       steps=[PlanStep(step_number=1, tool=METRICS, description="SUM profit GROUP BY product, TOP 5")],
       selected_tools=[METRICS]
     )
   Writes: intent="metrics", plan=<above>, selected_tools=[METRICS], current_step=0
   ↓
4. [router node body] → no-op
   [router_node edge] → selected_tools[0]=METRICS → returns "metrics"
   ↓
5. [metrics node]
   Reads: plan.steps[0] (tool parameters)
   Executes: DuckDB query (when implemented)
   Writes: tool_results=[ToolResult(tool=METRICS, step_number=1, success=True, data=[...])]
   ↓
6. [step_advance node]
   Reads: current_step=0
   Writes: current_step=1
   ↓
7. [router_node edge] → current_step=1 >= len(selected_tools)=1 → returns "synthesizer"
   ↓
8. [synthesizer node]
   Reads: query, plan.rationale, tool_results
   Builds prompt: system_prompt + user_msg with serialised ToolResult data
   Calls: llm.chat(messages, temperature=0.3)
   Gemini returns: "The top 5 products by profit are ..."
   Writes: final_answer="The top 5 products ...", messages=[Message(ASSISTANT, ...)]
   ↓
9. Graph reaches END
   ↓
10. Streamlit renders final_answer in chat panel
```

---

## Multi-step Execution

The multi-step loop is implemented via the `step_advance → router` static edge
combined with the `router_node` boundary check.

```
Every tool node has a static edge:  tool_node → step_advance
step_advance has a static edge:     step_advance → router
router has a conditional edge:      router → {tool | synthesizer | error_handler}
```

This creates an **explicit loop** in the graph. The loop terminates when
`current_step >= len(selected_tools)`, at which point the router exits to
`synthesizer`.

**There is no recursion limit** in the current implementation. For a plan
with N steps, the loop iterates exactly N times. Infinite loops are prevented
by the fact that `current_step` strictly increases and `selected_tools` is
fixed at planning time.

**Dependency ordering**: `PlanStep.depends_on` is defined in the schema but
is **not yet enforced by the router**. The current router executes steps in
the order they appear in `selected_tools`, regardless of `depends_on`. Parallel
or out-of-order execution is a planned future enhancement.

---

## Error Handling

| Failure mode | Where detected | Behaviour |
|---|---|---|
| Empty user query | Planner (guard clause) | Writes `errors=["Planner received an empty query."]`, plan=None |
| LLM exception in Planner | Planner (try/except) | Logs exception, writes `errors=["Planner failed: {exc}"]`, plan=None |
| Unknown `ToolName` in plan | Router (`_TOOL_NODE_MAP.get`) | Returns `"error_handler"` directly |
| Tool execution failure | Tool node (to be implemented in Phase 1) | Will return `ToolResult(success=False, error=...)` and optionally append to `errors` |
| LLM exception in Synthesizer | Synthesizer (try/except) | Returns fallback string without re-raising; does not write to `errors` |
| Errors present with no tool results | Synthesizer (guard clause) | Bypasses LLM, returns error-acknowledgment string directly |
| Any non-empty `errors` at router | Router (first check) | Routes to `error_handler` immediately |
| `error_handler` node | `_error_handler_node` | Logs errors, writes a user-facing error string to `final_answer` |

**Design principle**: Errors are accumulated in `state["errors"]` (append reducer)
rather than raised as exceptions. This allows the graph to always reach `END`
and always return a `final_answer`, even on failure.

---

## Conversation State

Multi-turn context is maintained through the `messages` field in `AgentState`.

```
Turn 1:
  query = "What is total revenue by region?"
  planner reads messages = []
  synthesizer appends: Message(role=ASSISTANT, content="West leads with $X...")
  messages = [Message(ASSISTANT, "West leads with $X...")]

Turn 2 (same session):
  query = "Which categories drive that?"
  planner reads messages[-10:] = [Message(ASSISTANT, "West leads with $X...")]
  planner includes prior answer as context in the LLM prompt
  synthesizer appends: Message(role=ASSISTANT, content="In the West, Technology...")
  messages = [Message(ASSISTANT, "West leads..."), Message(ASSISTANT, "Technology...")]
```

**Current implementation**: The application layer writes the user's current `query`
to state before each graph invocation. The planner's `_build_planner_messages`
helper includes the user's query as the final message and the prior `messages`
list (capped at last 10) as context. The synthesizer appends the assistant reply
at the end of each turn.

**Not yet implemented**: The Streamlit UI has no session-state management yet.
The `messages` accumulation works correctly at the graph level but is not wired
to a persistent UI session. This is a Phase 3 task.

**History truncation**: The planner takes `history[-10:]`, capping context at
10 prior messages to keep prompt size bounded. This is a hard-coded constant in
`_build_planner_messages`.
