# Architecture — Insight Copilot

## Overview

Insight Copilot is a LangGraph-powered analytical chatbot that translates
natural-language questions about a dataset into structured execution plans,
runs deterministic analytical tools, and synthesises the results into
analyst-style answers.

The architecture enforces a hard boundary between:

| Responsibility | Component |
|---|---|
| Natural-language understanding, intent classification, planning, result narration | LLM (Gemini) |
| SQL execution, calculations, trend analysis, chart rendering | Python / DuckDB / Plotly |

The LLM **never** invents dataset-derived numbers.  It only decides *what* to
compute and then *describes* the computed results.

---

## Component Map

```
┌─────────────────────────────────────────────────────────────────┐
│  Streamlit UI  (app.py)                                         │
│  ┌──────────────────────┐   ┌────────────────────────────────┐  │
│  │  Conversation panel  │   │  Execution Plan / Trace panel  │  │
│  └──────────────────────┘   └────────────────────────────────┘  │
└──────────────────────────────────┬──────────────────────────────┘
                                   │ invoke
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  LangGraph StateGraph  (agent/graph.py)                         │
│                                                                 │
│  START → [planner] → [router] ──────────────────────────────┐  │
│                          ▲                                   │  │
│                          │ (step_advance loops back)         │  │
│                          │                                   ▼  │
│              ┌───────────┴──────────────┐         [synthesizer] │
│              │   Tool nodes             │               │        │
│              │  ┌──────────────────┐    │               ▼        │
│              │  │  data_query      │    │             END        │
│              │  │  metrics         │    │                        │
│              │  │  trends          │    │                        │
│              │  │  charts          │    │                        │
│              │  └──────────────────┘    │                        │
│              └──────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Node Descriptions

### planner (`agent/planner.py`)
- **Input**: user query + conversation history
- **Output**: `AnalysisPlan` (intent, rationale, steps, selected_tools)
- **LLM call**: Yes — structured output (JSON mode)
- **Contract**: Must not invent data; only classifies intent and selects tools

### router (`agent/router.py`)
- **Input**: `selected_tools` + `current_step` from state
- **Output**: name of the next LangGraph node (string)
- **LLM call**: No — pure Python conditional logic
- **Contract**: Routes to the correct tool node or to `synthesizer`/`error_handler`

### step_advance (`agent/router.py::advance_step`)
- **Input**: `current_step`
- **Output**: `current_step + 1`
- **LLM call**: No
- **Purpose**: Enables the multi-step loop (router re-evaluates after each tool)

### Tool nodes (`tools/`)
- **Input**: relevant fields from `AgentState`
- **Output**: one `ToolResult` appended to `tool_results`
- **LLM call**: No — all computation is deterministic DuckDB / Plotly
- **Contract**: Must never call the LLM; must never fabricate data

### synthesizer (`agent/synthesizer.py`)
- **Input**: `query` + `plan` + `tool_results`
- **Output**: `final_answer` string; appends assistant `Message` to history
- **LLM call**: Yes — free-form chat (not structured output)
- **Contract**: Narrates tool results only; explicitly instructed not to invent numbers

---

## State (`agent/state.py`)

`AgentState` is a `TypedDict` that flows through every node.

| Field | Type | Reducer | Purpose |
|---|---|---|---|
| `messages` | `list[Message]` | `operator.add` | Full conversation history |
| `query` | `str` | last-write | Current user question |
| `intent` | `str` | last-write | Classified intent |
| `plan` | `AnalysisPlan \| None` | last-write | Structured execution plan |
| `selected_tools` | `list[ToolName]` | last-write | Ordered tool sequence |
| `current_step` | `int` | last-write | Loop counter for routing |
| `tool_results` | `list[ToolResult]` | `operator.add` | Accumulated tool outputs |
| `chart_artifacts` | `list[dict]` | last-write | Plotly figure dicts for UI |
| `final_answer` | `str \| None` | last-write | Synthesized narrative answer |
| `errors` | `list[str]` | `operator.add` | Accumulated error messages |

`operator.add` reducers allow multiple nodes to append to list fields without
overwriting each other's contributions.

---

## Data Layer

- Dataset files (CSV, Parquet, Excel) are loaded via `utils/data_loader.py`
  into an in-process DuckDB connection.
- All tools query the same DuckDB connection via parameterised SQL — no
  string interpolation of user input.
- The LLM never sees raw SQL or raw query results; it only sees serialised
  `ToolResult` objects via the synthesizer.

---

## LLM Provider Abstraction (`llm/`)

```
BaseLLM (abstract)
    └── GeminiLLM
    └── (future: OpenAILLM, AnthropicLLM, …)
```

`llm/factory.py::create_llm()` is the single entry-point.  Agent code
imports only `BaseLLM` and the factory — never provider-specific SDKs.

---

## Multi-step Execution Flow Example

**Query**: *"What is the seasonal trend in Technology sales and show me a chart?"*

```
START
  → planner  (produces: [TRENDS, CHARTS])
  → router   (current_step=0 → trends)
  → trends   (appends ToolResult)
  → step_advance (current_step → 1)
  → router   (current_step=1 → charts)
  → charts   (appends ToolResult with figure dict)
  → step_advance (current_step → 2)
  → router   (current_step=2 ≥ len(tools) → synthesizer)
  → synthesizer (produces final_answer)
  → END
```
