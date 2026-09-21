# Phase 3 Implementation Spec — Insight Copilot

**Branch**: `feat/phase-3-product-experience-and-advanced-analytics`  
**Depends on**: PR #6 & PR #7 merged to `main` (Phase 1 & Phase 2 Complete)  
**Goal**: Build the full production Streamlit UI with conversation persistence, interactive execution plan & tool trace panels, native Plotly chart rendering, and 3 advanced analytical capabilities (`anomaly_detection`, `correlation`, `segmentation`).

> This spec is the authoritative single source of truth for Phase 3.
> Do NOT alter Phase 1 or Phase 2 core tool logic or existing state architecture.
> Preserve the hard architectural principle:
> **LLM decides. Deterministic code executes. LLM explains.**

---

## Phase 2 Checklist — Verify Before Starting Phase 3

Confirm all of the following are true on the `main` branch:

- [x] `pytest tests/ -v` → 124 passed (108 offline unit tests + 16 live integration tests).
- [x] `utils/capability_registry.py` is the single source of truth for capabilities, schemas, and router mappings.
- [x] `tools/data_profile.py`, `tools/compare.py`, `tools/contribution.py`, `tools/profitability.py`, and `tools/variance.py` are fully implemented and verified on the canonical dataset.
- [x] Live on-device testing passes with `gemini-3.5-flash-lite`.
- [x] No Superstore dataset assumptions exist anywhere in the codebase.

---

## Phase 3 Scope — What We Are Building

Phase 3 consists of **two core tracks**:

```
Track A: Advanced Analytical Capabilities
  1. anomaly_detection  — statistical outlier discovery (IQR & Z-Score)
  2. correlation        — Pearson correlation with mandatory non-causation disclaimer
  3. segmentation       — multi-dimensional matrix analysis (e.g. Region × Category)

Track B: Full Streamlit Product Experience
  4. Conversational Chat Panel with multi-turn message history persistence
  5. Live Execution Plan & Tool Trace Panel (split layout)
  6. Inline Plotly Interactive Chart Rendering
  7. Graceful Error & Edge-case handling (empty results, ambiguous intent, quota exhaustion)
```

---

## Deliverable 1 — `anomaly_detection` Capability

### What it answers
> "Are there any unusually large or low orders/sales?", "Find revenue anomalies by region."

Detects statistical outliers deterministically in DuckDB without external ML libraries.

### File to create
`tools/anomaly_detection.py`

### Schema (`models/schemas.py`)
```python
class AnomalyRequest(BaseModel):
    metric: str = Field(..., description="Target numeric column (Units_Sold, Unit_Price, Revenue, Cost, Profit).")
    method: Literal["iqr", "zscore"] = Field(default="iqr", description="Statistical outlier detection method.")
    threshold: float = Field(default=1.5, ge=0.5, le=5.0, description="Multiplier for IQR (e.g. 1.5) or z-score cut-off (e.g. 2.5 or 3.0).")
    group_by: str | None = Field(default=None, description="Optional dimension to detect anomalies within groups.")
    filters: dict[str, Any] | None = Field(default=None, description="Optional equality filters.")

    @field_validator("metric")
    @classmethod
    def validate_metric_column(cls, v: str) -> str:
        for valid in NUMERIC_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid metric '{v}'. Must be one of {NUMERIC_COLUMNS}.")
```

### SQL Pattern & Output Contract
**IQR Method**:
```sql
WITH stats AS (
  SELECT
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY Revenue) AS q1,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY Revenue) AS q3
  FROM dataset
  WHERE <filters>
)
SELECT Date, Region, Product, Salesperson, Category, Revenue,
       ROUND(q1, 2) AS q1, ROUND(q3, 2) AS q3,
       ROUND(Revenue - (q3 + 1.5 * (q3 - q1)), 2) AS anomaly_score
FROM dataset, stats
WHERE Revenue > (q3 + 1.5 * (q3 - q1)) OR Revenue < (q1 - 1.5 * (q3 - q1))
ORDER BY Revenue DESC
LIMIT 50;
```

**Output in `ToolResult.data`**:
```python
{
    "metric": "Revenue",
    "method": "iqr",
    "threshold": 1.5,
    "anomalies_found": int,
    "rows": [
        {
            "Date": "2024-06-15",
            "Region": "West",
            "Product": "Laptop Pro",
            "Revenue": 28500.0,
            "q1": 4200.0,
            "q3": 11800.0,
            "anomaly_type": "high"
        }
    ]
}
```

### Tasks
- [ ] Add `ANOMALY_DETECTION = "anomaly_detection"` to `ToolName` in `models/schemas.py`.
- [ ] Implement `AnomalyRequest` in `models/schemas.py`.
- [ ] Implement `execute_anomaly_detection()` and `anomaly_detection_tool_node()` in `tools/anomaly_detection.py`.
- [ ] Register in `utils/capability_registry.py` under `"ADVANCED"`.
- [ ] Wire node and edges in `agent/graph.py`.
- [ ] Write `tests/test_anomaly_detection.py` (minimum 8 tests).

---

## Deliverable 2 — `correlation` Capability

### What it answers
> "Is there a relationship between Units_Sold and Revenue?", "Do discounts or price correlate with volume?"

Computes Pearson correlation coefficient (`CORR(x, y)`) directly in DuckDB.

### File to create
`tools/correlation.py`

### Schema (`models/schemas.py`)
```python
class CorrelationRequest(BaseModel):
    field_a: str = Field(..., description="First numeric column.")
    field_b: str = Field(..., description="Second numeric column.")
    group_by: str | None = Field(default=None, description="Optional dimension to calculate correlation across subsets.")
    filters: dict[str, Any] | None = Field(default=None, description="Optional equality filters.")

    @field_validator("field_a", "field_b")
    @classmethod
    def validate_numeric_fields(cls, v: str) -> str:
        for valid in NUMERIC_COLUMNS:
            if v.lower() == valid.lower():
                return valid
        raise ValueError(f"Invalid column '{v}'. Must be one of {NUMERIC_COLUMNS}.")
```

### SQL Pattern & Output Contract
```sql
SELECT
  ROUND(CORR(Units_Sold, Revenue), 4) AS correlation_coefficient,
  COUNT(*) AS sample_size
FROM dataset
WHERE <filters> AND Units_Sold IS NOT NULL AND Revenue IS NOT NULL;
```

**Output in `ToolResult.data`**:
```python
{
    "field_a": "Units_Sold",
    "field_b": "Revenue",
    "correlation_coefficient": 0.8412,
    "sample_size": 1960,
    "interpretation": "strong positive correlation",
    "caveat": "Correlation does not imply causation."
}
```

### Tasks
- [ ] Add `CORRELATION = "correlation"` to `ToolName`.
- [ ] Implement `CorrelationRequest` in `models/schemas.py`.
- [ ] Implement `execute_correlation()` and `correlation_tool_node()` in `tools/correlation.py`.
- [ ] Ensure output includes explicit non-causal disclaimer.
- [ ] Register in `utils/capability_registry.py`.
- [ ] Wire in `agent/graph.py`.
- [ ] Write `tests/test_correlation.py` (minimum 8 tests).

---

## Deliverable 3 — `segmentation` Capability

### What it answers
> "Show me the Region by Category matrix for Profit", "Break down Revenue across Salesperson and Product."

Performs multi-dimensional aggregated grouping across 2 distinct categorical columns.

### File to create
`tools/segmentation.py`

### Schema (`models/schemas.py`)
```python
class SegmentationRequest(BaseModel):
    metric: str = Field(..., description="Target numeric column.")
    dimension_primary: str = Field(..., description="Primary categorical axis (e.g. 'Region').")
    dimension_secondary: str = Field(..., description="Secondary categorical axis (e.g. 'Category').")
    aggregation: Literal["sum", "avg", "count"] = Field(default="sum", description="Aggregation function.")
    filters: dict[str, Any] | None = Field(default=None, description="Optional equality filters.")
    limit: int = Field(default=50, ge=1, le=200, description="Max combinations returned.")
```

### Tasks
- [ ] Add `SEGMENTATION = "segmentation"` to `ToolName`.
- [ ] Implement `SegmentationRequest` in `models/schemas.py`.
- [ ] Implement `execute_segmentation()` and `segmentation_tool_node()` in `tools/segmentation.py`.
- [ ] Register in `utils/capability_registry.py`.
- [ ] Wire in `agent/graph.py`.
- [ ] Write `tests/test_segmentation.py` (minimum 8 tests).

---

## Deliverable 4 — Production Streamlit UI (`app.py`)

### What it provides
A responsive, transparent, and reproducible analytical user experience.

### Exact Features
1. **Chat Interaction & State Management**:
   - Persist conversation history in `st.session_state.messages`.
   - Maintain multi-turn memory passing previous context cleanly into `create_initial_state(prompt, history)`.
   - Clear conversation button (`st.sidebar.button("Clear Chat")`).

2. **Execution Plan Trace Panel (Split View)**:
   - Left Column (60%): Interactive chat history, assistant explanations, and inline Plotly charts.
   - Right Column (40%): Real-time inspectable execution plan:
     - Classified `Intent` with badge.
     - Analytical `Rationale` written by Planner.
     - Numbered `PlanStep` cards displaying tool names, descriptions, dependencies, and JSON parameters.
     - Expandable `ToolResult` outputs with formatted tables (`st.dataframe`) and JSON inspection.

3. **Inline Plotly Chart Rendering**:
   - Automatically renders interactive dark-themed figures from `final_state["chart_artifacts"]` right below the corresponding assistant response.

4. **Sidebar Metadata & Dataset Health**:
   - Displays canonical dataset status, row count, column list, and quick metric summaries.
   - Model selection badge showing active Gemini model.

5. **Error & Edge-Case Handling**:
   - Graceful alert banner when API quota limits (429) or network issues occur.
   - Empty result acknowledgment (e.g., query for nonexistent salesperson returns friendly message instead of traceback).

---

## Implementation Order

```
Step 1  Anomaly Detection Tool  → tests/test_anomaly_detection.py pass
Step 2  Correlation Tool        → tests/test_correlation.py pass
Step 3  Segmentation Tool       → tests/test_segmentation.py pass
Step 4  Streamlit app.py UI     → full two-column layout, trace panel, charts
Step 5  End-to-End Verification → test app launch & multi-turn flows
```

---

## PR Strategy

Phase 3 will be delivered in **two focused PRs**:

- **PR #8** — `feat/phase-3a-advanced-analytical-tools`:
  - `anomaly_detection`, `correlation`, `segmentation` tools and tests.
  - Schema additions and capability registry registrations.
- **PR #9** — `feat/phase-3b-streamlit-product-ui`:
  - Full `app.py` overhaul with two-column layout, plan trace, chart rendering, and conversation management.
  - Documentation updates for Phase 3 completion.

---

## Final Acceptance Criteria — Phase 3 Complete

- [ ] All offline unit tests pass (`≥135 tests`).
- [ ] `anomaly_detection` accurately identifies statistical outliers on the canonical dataset.
- [ ] `correlation` outputs `CORR()` with explicit non-causal disclaimer.
- [ ] `segmentation` returns 2-dimensional cross-tabulation.
- [ ] `streamlit run app.py` launches cleanly without warnings or errors.
- [ ] User can submit a natural-language query and see the execution plan, tool trace, and grounded answer.
- [ ] Charts render natively in the UI using `st.plotly_chart`.
- [ ] Multi-turn conversation persists context across successive turns in the same session.
