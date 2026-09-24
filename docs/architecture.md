# Architecture — Insight Copilot

> **System Status**: Full Release Candidate architecture incorporating all 13 deterministic analytical capabilities, two-tier Bronze/Silver data architecture, pre-execution plan validation, dependency-aware routing, Google GenAI SDK integration, and full operational telemetry.

---

## System Overview

Insight Copilot is an **analytical agent**, not a chatbot with SQL attached.
The distinction matters architecturally:

- A chatbot answers questions by generating text.
- An analytical agent **plans an investigation**, **executes deterministic tools**
  to gather evidence, and **synthesises grounded conclusions** from that evidence.

Every number in Insight Copilot's answers comes from DuckDB, not from the LLM.
The LLM contributes language — understanding, planning, and narration — not computation.

```
LLM decides.       → Structured AnalysisPlan with typed PlanStep contracts.
Deterministic code executes. → Parameterized DuckDB SQL & Plotly rendering.
LLM explains.      → Executive synthesis with mandatory [Step X] citations.
```

### Major Components

| Component | File(s) | Responsibility |
|---|---|---|
| **Streamlit UI** | `app.py` | Renders split-screen workspace with independent chat and analysis inspector scroll containers, real-time tool trace, Plotly figures, and telemetry. |
| **LangGraph StateGraph** | `agent/graph.py` | Wires all nodes, static edges, and conditional routing into a compiled executable DAG. |
| **AgentState & State Loader** | `agent/state.py` | `TypedDict` separating persistent conversation state (`messages`) from clean per-turn execution state. `create_initial_state` resets execution fields on each turn. |
| **Planner** | `agent/planner.py` | LLM node. Classifies intent and produces a structured `AnalysisPlan` with typed `PlanStep` parameters using `BaseLLM` structured output. |
| **Pre-Execution Validator** | `agent/validator.py` | Deterministic validator checking step numbering, DAG acyclicity, schema validation, and registered capabilities before dispatch. |
| **Router** | `agent/router.py` | Pure-Python conditional edge. Validates step dependencies (`depends_on`) and dispatches to the correct tool node. No LLM call. |
| **`advance_step`** | `agent/router.py` | Increments `current_step` after each tool completes, driving the multi-step loop. |
| **Analytical Capability Nodes** | `tools/` | 13 deterministic execution nodes. Parse validated Pydantic parameters, execute DuckDB SQL or Plotly renders, and return `ToolResult`. |
| **Capability Registry** | `utils/capability_registry.py` | Authoritative registry of all 13 analytical capabilities, input schemas, and LangGraph tool node bindings. |
| **Data Layer** | `utils/data_loader.py` | Ingests `Sales_Dataset_2024.xlsx` → `sales_dataset.parquet`, registers Bronze (`raw_dataset`) and Silver (`dataset`) DuckDB views. |
| **Synthesizer** | `agent/synthesizer.py` | LLM node. Receives serialised `ToolResult` objects, calls `BaseLLM`, and returns an analyst-style answer grounded entirely in tool evidence. |
| **LLM Provider** | `llm/` | `BaseLLM` abstract interface + `GeminiLLM` (production: `gemini-3.5-flash`) primary provider and `GroqLLM` (`openai/gpt-oss-120b`) optional fallback wrapped via `FallbackLLM`. Factory in `llm/factory.py`. |
| **Schemas** | `models/schemas.py` | Pydantic contracts: `AnalysisPlan`, `PlanStep`, `ToolResult`, `DatasetSchema`, and 13 capability input schemas. |
| **Prompts** | `utils/prompts.py` | Centralised system prompts for planner and synthesizer. Dataset schema summary injected dynamically. |
| **Logging & Telemetry** | `utils/logging_config.py` | Structured run-level logging with `SensitiveDataFilter` secret redaction and rotating file handlers. |

---

## Architecture Diagram

```mermaid
flowchart TD
    U([User / Business Leader]) -->|Natural Language Question| ST[Streamlit UI\napp.py]
    ST -->|create_initial_state| START([START])

    START --> PL[planner\nagent/planner.py]
    PL -->|AnalysisPlan with typed PlanSteps| VAL[validator\nagent/validator.py]
    VAL -->|Validated Plan| RT[router\nagent/router.py]

    subgraph CR["Authoritative Capability Registry (13 Registered Tools)"]
        CAPLIST["Available Capabilities:\n• data_profile  • data_query  • data_clean\n• metrics  • trends  • compare  • contribution\n• profitability  • variance\n• anomaly_detection  • correlation  • segmentation\n• charts"]
    end

    PL -. "Injected Capabilities & Schema" .-> CR
    VAL -. "Schema & Registry Check" .-> CR

    RT -->|Pre-execution Error / Failed Dependency| EH[error_handler\nagent/router.py]
    RT -->|All steps complete / empty plan| SY[synthesizer\nagent/synthesizer.py]
    
    RT -->|1. data_access| DA[data_query / data_profile / data_clean]
    RT -->|2. core_analytics| CA[metrics / trends / compare / contribution / profitability / variance]
    RT -->|3. advanced_stats| AS[anomaly_detection / correlation / segmentation]
    RT -->|4. presentation| CH[charts]

    DA & CA & AS & CH -->|ToolResult appended| SA[step_advance\nagent/router.py]
    SA -->|current_step + 1| RT

    DA & CA & AS -->|Parameterized SQL| DB[(DuckDB Session Views:\n'raw_dataset' Bronze\n'dataset' Silver)]
    DB -->|Verified Result Rows| DA & CA & AS

    CA & DA & AS -..->|Upstream Data Rows| CH

    SY -->|final_answer with [Step X] Citations| END_([END])
    EH -->|final_answer with Diagnostic Guidance| END_

    subgraph LLM["Gemini Engine (google-genai SDK)"]
        PL_LLM[structured_chat\nAnalysisPlan response_schema]
        SY_LLM[chat\nGrounding & Synthesis]
    end

    PL -.- |Prompt + Schema + History| PL_LLM
    SY -.- |Prompt + Tool Results + History| SY_LLM
```

---

## Data Layer & Parquet Runtime

The canonical dataset for Insight Copilot is **`Sales_Dataset_2024.xlsx`**,
bundled in `data/`.

| Step | File | How |
|---|---|---|
| Source | `data/Sales_Dataset_2024.xlsx` | 2,000 rows, 10 columns — the immutable original |
| Runtime | `data/sales_dataset.parquet` | Auto-generated by `ensure_parquet_dataset()` on first run |
| DuckDB View | In-memory `dataset` | Registered by `get_connection()` via `CREATE VIEW dataset AS SELECT * FROM read_parquet(...)` |

The source Excel file is **never modified**. The Parquet file is a reproducible
artefact — delete it and it regenerates. All analytical queries target the
DuckDB view, never the original file.

### Canonical Schema (10 Fields)

| Column | DuckDB Type | Semantic Role | Groupable | Metric | Temporal |
|---|---|---|---|---|---|
| `Date` | TIMESTAMP | time | ✓ | — | ✓ |
| `Region` | VARCHAR | dimension | ✓ | — | — |
| `Product` | VARCHAR | dimension | ✓ | — | — |
| `Salesperson` | VARCHAR | dimension | ✓ | — | — |
| `Category` | VARCHAR | dimension | ✓ | — | — |
| `Units_Sold` | DOUBLE | metric | — | ✓ | — |
| `Unit_Price` | DOUBLE | metric | — | ✓ | — |
| `Revenue` | DOUBLE | metric | — | ✓ | — |
| `Cost` | DOUBLE | metric | — | ✓ | — |
| `Profit` | DOUBLE | metric | — | ✓ | — |

> **No other columns exist**. Do not reference `Order ID`, `Customer`,
> `Segment`, `Ship Date`, `Discount`, `Sub-Category`, `Country`, `State`,
> or `City` anywhere in prompts, tests, or documentation.
> Those belong to a different dataset.

---

## Data Quality & Cleaning Philosophy

Data quality findings are **observable evidence**, not silent corrections.

```
RAW SOURCE (Sales_Dataset_2024.xlsx)
        ↓
VALIDATION / PROFILING (validate_dataset, data_profile capability)
        ↓
RUNTIME REPRESENTATION (sales_dataset.parquet → DuckDB dataset view)
        ↓
ANALYSIS (deterministic tool execution)
```

### Principles

1. **Do not silently mutate the canonical source.** If 7 rows contain negative
   profit, the agent must report `"7 rows contain negative profit."` rather
   than deleting them before analysis.

2. **Data quality findings become explicit `ToolResult` evidence.** The
   `data_profile` capability surfaces missing values, duplicates,
   invalid dates, and statistical anomalies as structured output that the
   synthesizer can narrate honestly.

3. **Any future cleaning or transformation layer must be:**
   - Explicit — a named, documented transformation step
   - Deterministic — same input always produces same output
   - Testable — a unit test can verify the transformation
   - Non-destructive — the original source file is unchanged

4. **Validation at load time** (`validate_dataset()`) checks structural
   integrity (row count, column presence, type compatibility) but does not
   modify rows. Structural failures abort loading with a clear error message.

---

## Capability Registry Architecture

### Why a Registry

The **Capability Registry** (`utils/capability_registry.py`) is the single authoritative source of truth for all 13 analytical capabilities. Everything — the planner prompt context, the router's node dispatch map, and parameter contract validation — is derived dynamically from the registry.

- Adding a new capability requires registering it once in the `REGISTRY` dict.
- Input schemas, output descriptions, and category metadata are defined in one central location.
- Planner prompts and router dispatch maps are dynamically generated from the registry, eliminating dual sources of truth.

### Capability Definition

Each registered capability has the following attributes:

```
Capability
├── name                      str              — canonical identifier used in plans and routing
├── category                  str              — DATA_ACCESS | CORE_ANALYSIS | ADVANCED | PRESENTATION
├── description               str              — one-sentence description for the planner prompt
├── input_schema              type[BaseModel]  — Pydantic model that validates PlanStep.parameters
├── output_description        str              — description of what ToolResult.data will contain
├── deterministic             bool             — True for all DuckDB/Plotly tools; False if LLM involved
├── independent               bool             — can run as the first (or only) step in a plan
├── consumes_previous_results bool             — requires data from a prior ToolResult (e.g. charts)
└── node_name                 str              — LangGraph node name used in router dispatch map
```

### Registry-Derived Integration

The planner system prompt dynamically retrieves the capability context via:

```python
get_planner_context() -> str
```
Returns a formatted summary of all 13 registered capabilities, their input parameters, and output contracts, injected dynamically into `PLANNER_SYSTEM_PROMPT` alongside the dataset schema.

The router's node dispatch map is derived from the registry via:

```python
get_node_map() -> dict[ToolName, str]
```
Returns `{ToolName(cap.name): cap.node_name}` for conditional edge routing.

---

## Capability Categories & Implementation Status

### DATA ACCESS

| Capability | Description | Status |
|---|---|---|
| `data_profile` | Dataset overview: row count, columns, types, missing values, cardinality, date range, numeric ranges, data quality warnings | ✅ Implemented |
| `data_query` | Filtered SELECT with column selection, equality filters, sorting, row limits | ✅ Implemented |
| `data_clean` | Interactive dimension hygiene: casing standardization, fuzzy typo clustering (e.g. `Easst` → `East`), and null value imputation on Silver `dataset` view | ✅ Implemented |

### CORE ANALYSIS

| Capability | Description | Status |
|---|---|---|
| `metrics` | Aggregated computations: SUM, AVG, COUNT, MIN, MAX with GROUP BY and ranking | ✅ Implemented |
| `trends` | Temporal aggregations over `Date` at day/week/month/quarter/year granularity | ✅ Implemented |
| `compare` | Side-by-side comparison of two entities or periods with absolute and percentage delta | ✅ Implemented |
| `contribution` | Percentage and absolute contribution of segments to a total | ✅ Implemented |
| `profitability` | Revenue, cost, profit, and derived profit margin analysis (Profit / Revenue) | ✅ Implemented |
| `variance` | Period-over-period or group-to-group change: baseline, comparison, absolute delta, % delta | ✅ Implemented |

### ADVANCED ANALYSIS

| Capability | Description | Status |
|---|---|---|
| `anomaly_detection` | Statistical detection of unusual observations (IQR, z-score) — no ML required | ✅ Implemented |
| `correlation` | Pearson correlation between numeric fields — explicitly not causal inference | ✅ Implemented |
| `segmentation` | Cross-dimensional analysis: Region × Category, Salesperson × Category, etc. | ✅ Implemented |

### PRESENTATION

| Capability | Description | Status |
|---|---|---|
| `charts` | Plotly figure generation (bar, line, scatter) from prior ToolResult data — no DuckDB query | ✅ Implemented |

---

## Capability Rationale

### `data_profile`

**User question**: "What does this dataset look like?"

**Why the four Phase 1 tools are insufficient**:
`data_query` can return raw rows and `metrics` can return counts, but neither
provides a structured overview of data quality, cardinality, or the date range
in a single, purpose-built output.

**What it should produce**:
```json
{
  "row_count": 2000,
  "column_count": 10,
  "date_range": {"min": "2024-01-01", "max": "2024-12-31"},
  "numeric_ranges": {
    "Revenue": {"min": 120.0, "max": 8400.0, "mean": 2150.3},
    "Profit": {"min": -210.0, "max": 3100.0}
  },
  "categorical_cardinality": {
    "Region": 4, "Category": 3, "Product": 25, "Salesperson": 10
  },
  "data_quality_warnings": [
    "7 rows contain negative Profit",
    "0 missing values across all columns"
  ]
}
```

**Deterministic**: Yes (DuckDB aggregate queries).
**Parameters**: None required; runs against the registered `dataset` view.
**Dependencies**: None.

---

### `compare`

**User questions**:
- "How did North compare to South this year?"
- "Was Q1 better than Q2 for revenue?"
- "Compare Technology vs Furniture profit."

**Why `metrics` alone is insufficient**:
`metrics` can compute aggregations for a single group at a time.
`compare` needs two parallel aggregations with automatic delta computation
(absolute and percentage), presented as a side-by-side structure the
synthesizer can narrate directly.

**What it should produce**:
```json
{
  "metric": "Revenue",
  "aggregation": "sum",
  "entity_a": {"label": "North", "value": 425000.0},
  "entity_b": {"label": "South", "value": 318000.0},
  "absolute_delta": 107000.0,
  "pct_delta": 33.6
}
```

**Deterministic**: Yes.
**Input parameters**: `metric`, `aggregation`, `dimension`, `value_a`, `value_b`, optional `filters`.
**Dependencies**: None (can run independently).

---

### `contribution`

**User questions**:
- "Which region drives the most revenue?"
- "What percentage of total profit comes from Technology?"
- "Rank categories by their contribution to total sales."

**Why `metrics` alone is insufficient**:
`metrics` with `GROUP BY` returns absolute values per group. `contribution`
adds the percentage-of-total computation (relative share), which requires
knowing the grand total — a two-pass query or a window function. The output
is a ranked list of absolute + relative contributions, not just raw values.

**What it should produce**:
```json
[
  {"Region": "North", "Revenue": 425000.0, "pct_of_total": 38.2},
  {"Region": "West",  "Revenue": 310000.0, "pct_of_total": 27.9},
  ...
]
```

**Deterministic**: Yes (DuckDB window function: `SUM(metric) OVER () AS total`).
**Input parameters**: `metric`, `dimension`, optional `filters`.
**Dependencies**: None.

---

### `profitability`

**User questions**:
- "Which products have the highest profit margin?"
- "Is the West region more profitable than the East?"
- "Which category generates revenue but low profit?"

**Why `metrics` alone is insufficient**:
Profit margin is a derived metric (`Profit / Revenue`). `metrics` can aggregate
either `Profit` or `Revenue`, but not compute the ratio in a single step.
`profitability` is a dedicated capability that expresses the relationship between
revenue, cost, profit, and margin simultaneously — preventing the common mistake
of treating high revenue as equivalent to high profitability.

**Derived metric**:
```
Profit Margin = Profit / Revenue
```

**What it should produce**:
```json
[
  {
    "Product": "Widget A",
    "Revenue": 84000.0,
    "Cost": 52000.0,
    "Profit": 32000.0,
    "profit_margin_pct": 38.1
  },
  ...
]
```

**Deterministic**: Yes.
**Input parameters**: `dimension` (group by column), optional `filters`, `limit`.
**Dependencies**: None.

---

### `variance`

**User questions**:
- "How did profit change from H1 to H2?"
- "Which months showed the biggest month-over-month revenue change?"
- "Compare this quarter's performance to last quarter."

**Why `trends` alone is insufficient**:
`trends` returns a time series. `variance` computes the **change between adjacent
periods** — the delta — which requires a self-join or a LAG window function.
The output is designed specifically for "what changed and by how much" questions.

**What it should produce**:
```json
[
  {
    "period": "2024-01",
    "Revenue": 185000.0,
    "prev_Revenue": null,
    "absolute_change": null,
    "pct_change": null
  },
  {
    "period": "2024-02",
    "Revenue": 203000.0,
    "prev_Revenue": 185000.0,
    "absolute_change": 18000.0,
    "pct_change": 9.73
  },
  ...
]
```

**Deterministic**: Yes (DuckDB `LAG()` window function).
**Input parameters**: `metric`, `granularity`, optional `group_by`, optional `filters`.
**Dependencies**: None (can run independently, or after `trends` for context).

---

### `anomaly_detection`

**User questions**:
- "Are there any unusually large or small orders?"
- "Which salespeople show unexpectedly low profit margins?"
- "Find outliers in the revenue data."

**Implementation approach (deterministic, no ML)**:
- **IQR method**: Flag values below `Q1 - 1.5×IQR` or above `Q3 + 1.5×IQR`.
- **Z-score method**: Flag values where `|z| > threshold` (default: 2.5).

Both are computable with DuckDB `PERCENTILE_CONT` and standard window functions.

**Important constraint**: Correlation does not establish causation.
Anomaly detection surfaces observations, not explanations.
The synthesizer must present flagged rows as *observations requiring investigation*,
not as errors or fraud.

**Deterministic**: Yes.
**Input parameters**: `metric`, `method` (`iqr` | `zscore`), optional `group_by`, optional `threshold`.
**Dependencies**: None.
**Phase**: 3.

---

### `correlation`

**User questions**:
- "Is there a relationship between Units_Sold and Revenue?"
- "Does higher Unit_Price correlate with lower Units_Sold?"

**Available numeric fields**: `Units_Sold`, `Unit_Price`, `Revenue`, `Cost`, `Profit`.

**Mandatory disclaimer in all synthesizer output**:
> Correlation does not establish causation.

**Deterministic**: Yes (DuckDB `CORR()` aggregate function).
**Input parameters**: `field_a`, `field_b`, optional `group_by`, optional `filters`.
**Phase**: 3.

---

### `segmentation`

**User questions**:
- "Which region-category combinations are most profitable?"
- "How does each salesperson perform across product categories?"

**Examples**:
- `Region × Category` — 4 × 3 = 12 cells
- `Region × Product` — multi-level breakdown
- `Salesperson × Category` — performance matrix

**Deterministic**: Yes (DuckDB multi-column `GROUP BY`).
**Input parameters**: `metric`, `dimensions` (list of 2 columns), optional `filters`.
**Phase**: 3.

---

## Investigation Workflow

The agent does not treat every user question as a one-shot query.
Complex questions require a **multi-step investigation** where later steps
consume evidence produced by earlier steps.

### Workflow Model

```
User question
      ↓
Investigation plan (AnalysisPlan)
      ↓
Capability selection (ordered PlanSteps with depends_on)
      ↓
Dependency-aware execution (Router validates before dispatching)
      ↓
Deterministic evidence (ToolResults)
      ↓
Grounded synthesis (Synthesizer narrates only verified evidence)
```

**Principle: Evidence before explanation.**

Every analytical claim in the synthesizer's output must be traceable to
one or more `ToolResult` objects. The synthesizer is not permitted to
introduce numbers, causes, or conclusions that did not appear in a `ToolResult`.

### Concrete Investigation Example

**User question**: *"Why did profit decline in the second half of 2024?"*

This question cannot be answered with a single tool call.
A correct investigation plan:

```
Step 1 — trends
  metric: Profit, granularity: month
  Purpose: Confirm whether profit actually declined and identify the period.
  depends_on: []

Step 2 — compare
  metric: Profit, aggregation: sum, entity_a: H1 (Jan–Jun), entity_b: H2 (Jul–Dec)
  Purpose: Quantify the H1 vs H2 gap precisely.
  depends_on: [1]

Step 3 — contribution
  metric: Profit, dimension: Region
  Purpose: Identify which regions drove the most decline.
  depends_on: [2]

Step 4 — profitability
  dimension: Category
  Purpose: Identify whether the margin changed even if revenue stayed flat.
  depends_on: []

Step 5 — charts
  chart_type: line, x: period, y: total_profit
  Purpose: Visualise the monthly trend from Step 1.
  depends_on: [1]

Step 6 — synthesizer (not a tool, the terminal node)
  Receives: ToolResults from Steps 1–5.
  Produces: An evidence-grounded explanation using only verified numbers.
  Must not invent causes. Must attribute every claim to a step number.
```

The synthesizer's role in this investigation is **narrative**, not analytical.
It is explicitly prohibited from saying *"profit declined because X"* unless
a ToolResult demonstrated that X changed in the relevant period.

---

## LangGraph State

`AgentState` is defined in [`agent/state.py`](../agent/state.py) as a
`TypedDict` with `total=False`. LangGraph uses it as the single shared
memory object that every node reads from and writes to.

Fields with `Annotated[list[X], operator.add]` use a **reducer**: LangGraph
merges node return values by *appending* to the existing list rather than
replacing it. All other fields use **last-write-wins**.

### Field Reference

---

#### `messages`

```python
messages: list[Message]
```

| | |
|---|---|
| **Type** | `list[Message]` (Pydantic: `role: Role`, `content: str`, `metadata: dict`) |
| **Reducer** | `operator.add` — each node appends; no node can overwrite history |
| **Purpose** | Full conversation history across all turns. Planner reads last 10 entries. |
| **Written by** | Synthesizer (appends one `Message(role=ASSISTANT)` per turn) |
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
| **Purpose** | Raw natural-language question for the current turn. Reset each new query. |
| **Written by** | Application layer (before graph invocation) |
| **Read by** | Planner, Synthesizer |

---

#### `intent`

```python
intent: str
```

| | |
|---|---|
| **Type** | `str` (mirrors `Intent` enum: `"data_query"`, `"metrics"`, `"trend"`, `"chart"`, `"combined"`, `"unknown"`) |
| **Reducer** | Last-write-wins |
| **Purpose** | Classified analytical intent. Written as plain string for direct UI display. |
| **Written by** | Planner |
| **Read by** | UI trace panel |

---

#### `plan`

```python
plan: AnalysisPlan | None
```

| | |
|---|---|
| **Type** | `AnalysisPlan` (Pydantic: `intent`, `rationale`, `steps: list[PlanStep]`, `selected_tools`) or `None` |
| **Reducer** | Last-write-wins |
| **Purpose** | Structured execution plan. `None` until the planner runs or if planning fails. |
| **Written by** | Planner |
| **Read by** | Router (reads `plan.steps[current_step]` for parameter extraction and dependency validation), Synthesizer (rationale for synthesis prompt), UI (trace display) |

---

#### `selected_tools`

```python
selected_tools: list[ToolName]
```

| | |
|---|---|
| **Type** | `list[ToolName]` (enum: `DATA_QUERY`, `METRICS`, `TRENDS`, `CHARTS`) |
| **Reducer** | Last-write-wins |
| **Purpose** | Ordered list of capabilities to run this turn. Derived from `plan.selected_tools`. |
| **Written by** | Planner |
| **Read by** | Router (bounds check: `current_step >= len(selected_tools)`) |

---

#### `current_step`

```python
current_step: int
```

| | |
|---|---|
| **Type** | `int` |
| **Reducer** | Last-write-wins |
| **Purpose** | Zero-based index into `plan.steps`. Tracks which capability to dispatch next. Reset to `0` by Planner each turn. |
| **Written by** | Planner (resets to `0`), `advance_step` node (increments by `1`) |
| **Read by** | Router (dispatch decision), all tool nodes (to identify current `PlanStep`) |

---

#### `tool_results`

```python
tool_results: list[ToolResult]
```

| | |
|---|---|
| **Type** | `list[ToolResult]` (Pydantic: `tool`, `step_number`, `success: bool`, `data: Any`, `error: str \| None`) |
| **Reducer** | `operator.add` — each tool appends; earlier results are never overwritten |
| **Purpose** | Accumulated evidence from every capability execution in this turn. |
| **Written by** | Each tool node (appends one `ToolResult` per invocation) |
| **Read by** | Synthesizer (composes final answer), Charts tool (reads prior data), Router (dependency validation) |

---

#### `chart_artifacts`

```python
chart_artifacts: list[dict[str, Any]]
```

| | |
|---|---|
| **Type** | `list[dict]` — each dict is a Plotly figure serialised via `fig.to_dict()` |
| **Reducer** | Last-write-wins (list is manually accumulated by the charts tool) |
| **Purpose** | Plotly figures separated from the text answer so the UI renders them independently. |
| **Written by** | Charts tool (`render_chart_from_data` → `fig.to_dict()`) |
| **Read by** | Streamlit UI (`st.plotly_chart`) |

---

#### `final_answer`

```python
final_answer: str | None
```

| | |
|---|---|
| **Type** | `str` or `None` |
| **Reducer** | Last-write-wins |
| **Purpose** | Complete analyst-style response. Set by Synthesizer on success or `error_handler` on failure. `None` until the graph reaches one of those nodes. |
| **Written by** | Synthesizer, `error_handler_node` |
| **Read by** | Streamlit UI |

---

#### `errors`

```python
errors: list[str]
```

| | |
|---|---|
| **Type** | `list[str]` |
| **Reducer** | `operator.add` — errors from different nodes accumulate |
| **Purpose** | Collects error messages from any node. Router checks `errors` first on every evaluation — a non-empty list causes immediate redirect to `error_handler`. |
| **Written by** | Planner (on empty query or LLM exception), any tool node (on validation or execution failure) |
| **Read by** | Router (checked first), Synthesizer (guard clause) |

---

## Graph Nodes

### `planner`

**File**: [`agent/planner.py`](../agent/planner.py) — `build_planner_node(llm)` closure.

| | |
|---|---|
| **Responsibility** | Classify intent and produce a structured `AnalysisPlan`. The only LLM call in the planning phase. |
| **Reads from state** | `query`, `messages` |
| **Writes to state** | `intent`, `plan`, `selected_tools`, `current_step` (reset to `0`) |
| **LLM call** | `llm.structured_chat(messages, AnalysisPlan)` — Gemini JSON mode, temperature `0.0` |
| **On empty query** | Returns `intent=UNKNOWN`, `plan=None`, `selected_tools=[]`, appends to `errors` |
| **On LLM exception** | Logs exception, returns same failure state as empty query |
| **Next node** | Always `router` (static edge) |

**Context window**: System prompt + last 10 `messages` + dataset schema summary + current `query`.
History truncation is hard-coded at 10 turns in `_build_planner_messages`.

**Registry Integration**: The system prompt's capability list is dynamically generated from the Capability Registry (`get_planner_context()`). Parameter schemas for all registered capabilities are injected automatically.

---

### `router` (node body)

**File**: [`agent/router.py`](../agent/router.py) — `_passthrough_node`.

| | |
|---|---|
| **Responsibility** | No-op. Routing logic lives in the `router_node` conditional-edge function. |
| **Reads from state** | Nothing |
| **Writes to state** | Nothing |
| **Next node** | Determined by `router_node` conditional edge |

---

### `router_node` (conditional edge function)

**File**: [`agent/router.py`](../agent/router.py) — `router_node(state) -> str`.

Not a node — called by LangGraph's conditional edge mechanism after `router` executes.

| Priority | Condition | Returns |
|---|---|---|
| 1 | `len(errors) > 0` | `"error_handler"` |
| 2 | `len(selected_tools) == 0` or `plan is None` | `"synthesizer"` |
| 3 | `current_step >= len(selected_tools)` | `"synthesizer"` |
| 4 | `current_plan_step.depends_on` not satisfied by prior `ToolResult`s | `"error_handler"` |
| 5 | `selected_tools[current_step]` is a known `ToolName` | node name from `_TOOL_NODE_MAP` |
| 6 | `selected_tools[current_step]` is unknown | `"error_handler"` |

**Dependency & Pre-Execution Validation**: Dependency validation (priority 4) verifies that referenced step numbers have completed successfully. Pre-execution plan validation (`agent/validator.py`) additionally validates parameter schemas and DAG acyclicity before tool dispatch.

---

### `step_advance`

**File**: [`agent/router.py`](../agent/router.py) — `advance_step(state) -> dict`.

| | |
|---|---|
| **Responsibility** | Increment `current_step` by 1 after a tool completes. |
| **Reads** | `current_step` |
| **Writes** | `current_step` (incremented) |
| **Next node** | Always `router` (static edge) |

---

### `data_query` ✅ Implemented

**File**: [`tools/data_query.py`](../tools/data_query.py)

| | |
|---|---|
| **Responsibility** | Execute a parameterised filtered SELECT against `dataset`. |
| **Input contract** | `DataQueryRequest` — columns, filters, sort_by, sort_order, limit (≤100) |
| **Output** | `list[dict]` — raw rows matching the query |
| **Reads from state** | `plan`, `current_step` |
| **Writes to state** | `tool_results` (appends one `ToolResult`) |
| **Next node** | Always `step_advance` |

---

### `metrics` ✅ Implemented

**File**: [`tools/metrics.py`](../tools/metrics.py)

| | |
|---|---|
| **Responsibility** | Compute aggregated metrics via DuckDB `GROUP BY`. |
| **Input contract** | `MetricsRequest` — metric, aggregation, group_by, filters, limit, sort |
| **Supported aggregations** | SUM, AVG, COUNT, MIN, MAX, MEDIAN |
| **Output** | `list[dict]` — grouped aggregation rows |
| **Reads from state** | `plan`, `current_step` |
| **Writes to state** | `tool_results` (appends one `ToolResult`) |
| **Next node** | Always `step_advance` |

---

### `trends` ✅ Implemented

**File**: [`tools/trends.py`](../tools/trends.py)

| | |
|---|---|
| **Responsibility** | Temporal aggregation of a metric over `Date` using `DATE_TRUNC`. |
| **Input contract** | `TrendsRequest` — metric, date_column, granularity, group_by, filters |
| **Supported granularities** | `day`, `week`, `month`, `quarter`, `year` |
| **Output** | `list[dict]` — `{period: str, total_<metric>: float}` rows ordered by period |
| **Reads from state** | `plan`, `current_step` |
| **Writes to state** | `tool_results` (appends one `ToolResult`) |
| **Next node** | Always `step_advance` |

---

### `charts` ✅ Implemented

**File**: [`tools/charts.py`](../tools/charts.py)

| | |
|---|---|
| **Responsibility** | Render a Plotly figure from a prior tool's tabular data. Does not query DuckDB. |
| **Input contract** | `ChartRequest` — chart_type, x, y, color (optional), title (optional) |
| **Supported types** | `bar`, `line`, `scatter` |
| **Data source** | Most recent successful `ToolResult` with list data, or the step referenced in `depends_on` |
| **Output** | `fig.to_dict()` — Plotly figure dict in `ToolResult.data` and `chart_artifacts` |
| **Reads from state** | `tool_results`, `plan`, `current_step`, `chart_artifacts` |
| **Writes to state** | `tool_results` (appends figure `ToolResult`), `chart_artifacts` (appends figure dict) |
| **Next node** | Always `step_advance` |

---

### `synthesizer`

**File**: [`agent/synthesizer.py`](../agent/synthesizer.py) — `build_synthesizer_node(llm)` closure.

| | |
|---|---|
| **Responsibility** | Narrate `tool_results` into a grounded analyst-style answer. Evidence before explanation. |
| **Reads from state** | `query`, `plan`, `tool_results`, `errors` |
| **Writes to state** | `final_answer`, `messages` (appends assistant `Message`) |
| **LLM call** | `llm.chat(messages, temperature=0.3)` — free-form text |
| **On errors with no results** | Bypasses LLM; returns a safe error-acknowledgment string |
| **On LLM exception** | Returns fallback message without re-raising |
| **Next node** | `END` |

**Grounding contract**: The synthesizer prompt explicitly states:
> "Use ONLY the numbers and data provided in the tool results. Never invent figures."

Every number in the synthesizer's response must be traceable to a `ToolResult`.

---

### `error_handler`

**File**: [`agent/graph.py`](../agent/graph.py) — `_error_handler_node`.

| | |
|---|---|
| **Responsibility** | Terminal node for unrecoverable errors. Logs errors. Writes user-facing error string to `final_answer`. |
| **Reads from state** | `errors`, `final_answer` |
| **Writes to state** | `final_answer` (only if not already set) |
| **Next node** | `END` |

---

## Conditional Routing

The single conditional edge is attached to `router` and calls `router_node(state) -> str`.

### Decision Algorithm

```python
# Pseudocode from agent/router.py::router_node

if state["errors"]:                              # (1) abort on any error
    return "error_handler"

tools = state["selected_tools"]
plan  = state["plan"]
step  = state["current_step"]

if not tools or plan is None:                    # (2) nothing to run
    return "synthesizer"

if step >= len(tools) or step >= len(plan.steps):  # (3) all steps done
    return "synthesizer"

current_plan_step = plan.steps[step]

# (4) validate depends_on
if current_plan_step.depends_on:
    for dep_step_num in current_plan_step.depends_on:
        if not any(tr.step_number == dep_step_num and tr.success
                   for tr in state["tool_results"]):
            return "error_handler"

# (5) dispatch
return _TOOL_NODE_MAP.get(current_plan_step.tool, "error_handler")
```

---

## PlanStep Dependencies

`PlanStep` has two structurally important fields:

```python
class PlanStep(BaseModel):
    step_number: int          # 1-based position in the plan
    tool: ToolName            # capability to invoke
    description: str          # human-readable step description
    parameters: dict[str, Any]  # typed parameters for the capability's input schema
    depends_on: list[int]     # step_numbers that must complete successfully first
```

`depends_on` is already validated by the router on every dispatch.
It enables the agent to express analytical workflows where later steps
require evidence from earlier steps.

### Example: Multi-step Investigation with Dependencies

```
Plan for: "Show me a profit trend and highlight the worst month."

Step 1: trends
  parameters: {metric: "Profit", granularity: "month"}
  depends_on: []

Step 2: charts
  parameters: {chart_type: "line", x: "period", y: "total_profit"}
  depends_on: [1]   ← must have Step 1 data before rendering

Step 3: metrics
  parameters: {metric: "Profit", aggregation: "min", group_by: "Date"}
  depends_on: []    ← independent; can run alongside Step 1 conceptually
```

### Plan & Pre-Execution Validation Rules

- Referenced `step_number` in `depends_on` has a corresponding `ToolResult` with `success=True`.
- The capability's required input type (e.g. `charts` requires list data) is present in the referenced `ToolResult.data`.
- The `parameters` dict validates against the capability's `input_schema` before the tool node runs via `agent/validator.py` (failing fast with structured error guidance).

---

## Tool Architecture Boundary

There is a hard, enforced boundary between LLM reasoning and deterministic execution:

```
┌──────────────────────────────────────────────────────────┐
│                   LLM RESPONSIBILITY                      │
│                                                           │
│  • Natural-language understanding                         │
│  • Intent classification                                  │
│  • Selecting which capabilities to run and in what order  │
│  • Constructing structured parameters for each step       │
│  • Formulating investigation plans with depends_on        │
│  • Synthesising verified evidence into narrative          │
│                                                           │
│  Implemented in: planner.py, synthesizer.py               │
│  Temperature: 0.0 (planner), 0.3 (synthesizer)           │
└──────────────────────────────────────────────────────────┘
                             │
                      AnalysisPlan
                      (structured JSON)
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│              DETERMINISTIC RESPONSIBILITY                 │
│                                                           │
│  • All SQL queries (parameterised, column-validated)      │
│  • All aggregations (SUM, AVG, COUNT, MIN, MAX, MEDIAN)  │
│  • All temporal analysis (DATE_TRUNC, LAG window)        │
│  • All comparison and delta computation                   │
│  • All profitability margin derivation (Profit / Revenue) │
│  • All contribution percentage computation                │
│  • All statistical calculations (IQR, z-score)           │
│  • All correlation computation (CORR())                   │
│  • All chart rendering (Plotly)                           │
│  • All data validation and profiling                      │
│                                                           │
│  Implemented in: tools/, utils/data_loader.py, DuckDB    │
│  No LLM access within tool nodes                         │
└──────────────────────────────────────────────────────────┘
```

**Enforcement**: Tool nodes receive only `AgentState`. They have no reference
to any `BaseLLM` instance. They cannot call the LLM even by accident.
The `BaseLLM` is injected only into `build_planner_node` and
`build_synthesizer_node` via closure.

---

## Multi-step Execution Loop

```
Every tool node:  tool_node → step_advance  (static edge)
step_advance:     step_advance → router     (static edge)
router:           router → {tool | synthesizer | error_handler}  (conditional edge)
```

The loop terminates when `current_step >= len(selected_tools)`.
There is no recursion limit. For a plan with N steps, the loop iterates
exactly N times. Infinite loops are structurally impossible because
`current_step` strictly increases and `selected_tools` is fixed at planning time.

---

## Error Handling

| Failure mode | Detected where | Behaviour |
|---|---|---|
| Empty user query | Planner (guard clause) | `errors=["Planner received an empty query."]`, `plan=None` |
| LLM exception in Planner | Planner (`try/except`) | Logs, `errors=["Planner failed: {exc}"]`, `plan=None` |
| Invalid `ToolName` in plan | Router (`_TOOL_NODE_MAP.get`) | Returns `"error_handler"` |
| `depends_on` step not completed | Router (dependency loop) | Appends to `errors`, returns `"error_handler"` |
| Pydantic validation failure on parameters | Tool node (`model_validate`) | `ToolResult(success=False, error=...)`, graph continues |
| DuckDB query failure | Tool node (`try/except`) | `ToolResult(success=False, error=...)`, graph continues |
| LLM exception in Synthesizer | Synthesizer (`try/except`) | Returns fallback string; does not write to `errors` |
| `errors` non-empty at any router evaluation | Router (first check) | Routes immediately to `error_handler` |
| `error_handler` node | `_error_handler_node` | Logs errors, writes user-facing string to `final_answer` |

**Design principle**: Errors are accumulated in `state["errors"]` (append reducer)
rather than raised as exceptions. The graph always reaches `END` and always
returns a `final_answer`, even on failure.

---

## Conversation State & Multi-turn Context

Multi-turn context is maintained through the `messages` field.

```
Turn 1:
  query = "What is total revenue by region?"
  planner reads messages = []
  synthesizer appends: Message(ASSISTANT, "The North region leads with $425k...")
  messages = [Message(USER, "What is total..."), Message(ASSISTANT, "North leads...")]

Turn 2 (same session):
  query = "Which categories drive that?"
  planner reads messages[-10:] including prior assistant message
  planner produces plan aware that "that" refers to North's revenue
  synthesizer appends: Message(ASSISTANT, "In the North, Technology contributes 42%...")
```

**History truncation**: The planner takes `history[-10:]`, capping context at
10 prior messages to keep prompt size bounded.

**Session persistence**: `create_initial_state(query, history)` separates persistent
`messages` from per-turn execution state. Execution fields (`tool_results`,
`chart_artifacts`, `errors`, `plan`, `current_step`) are reset clean on each turn.

---

## Routing Examples

**Single-tool query**: *"What is total revenue by region?"*

```
Plan: selected_tools = [METRICS]

router (step=0): METRICS → "metrics"
metrics executes → ToolResult(success=True, data=[...]) → step_advance (step=1)
router (step=1): 1 >= 1 → "synthesizer"
synthesizer → END
```

**Multi-tool investigation**: *"Show a chart of monthly profit trends."*

```
Plan: selected_tools = [TRENDS, CHARTS]

router (step=0): TRENDS → "trends"
trends executes → ToolResult(success=True) → step_advance (step=1)
router (step=1): CHARTS → dependency check (step 1 exists and succeeded) → "charts"
charts reads trends data → renders Plotly figure → step_advance (step=2)
router (step=2): 2 >= 2 → "synthesizer"
synthesizer → END
```

**Failed dependency**: *"Chart the data"* (charts step depends_on a trends step that failed)

```
router (step=1): CHARTS → depends_on=[0] → ToolResult(step=0, success=False)
→ dependency not satisfied → errors=["...dependency check failed"]
→ "error_handler"
error_handler → END (final_answer = user-facing error message)
```
