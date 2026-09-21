# Insight Copilot

A LangGraph-powered analytical assistant that translates natural-language
questions about a dataset into deterministic computations and synthesises the
results into analyst-style answers.

---

## What it does

1. **Understands your question** — classifies intent (data retrieval, metric
   computation, trend analysis, or visualisation).
2. **Creates an explicit plan** — produces a structured `AnalysisPlan` that
   is visible in the UI before execution begins.
3. **Executes deterministic tools** — runs DuckDB queries, computes aggregations,
   performs trend analysis, and renders Plotly charts.
4. **Synthesises an answer** — the LLM narrates the tool results in plain English
   without inventing any numbers.
5. **Supports multi-turn conversation** — maintains context across questions.

---

## Architecture

```
User question
     │
     ▼
 [Planner]  ──► AnalysisPlan (intent + steps + rationale)
     │
     ▼
 [Router]   ──► dispatches to tool nodes in sequence
     │
     ├──► [data_query]  ──► DuckDB SELECT
     ├──► [metrics]     ──► DuckDB aggregation
     ├──► [trends]      ──► DuckDB window functions
     └──► [charts]      ──► Plotly figure
     │
     ▼
 [Synthesizer]  ──► LLM narrates tool results
     │
     ▼
 Final answer + chart artifacts
```

See [`docs/architecture.md`](docs/architecture.md) for the full design.

---

## Tech stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph |
| LLM | Gemini (via `google-generativeai`) |
| Data engine | DuckDB |
| Data manipulation | Pandas |
| Visualisation | Plotly |
| UI | Streamlit |
| Validation | Pydantic v2 |
| Tests | pytest |

---

## Getting started

### 1. Clone and install dependencies

```bash
git clone https://github.com/sankett28/insight-copilot.git
cd insight-copilot
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### 2. Configure environment

```bash
copy .env.example .env
# Edit .env and set GEMINI_API_KEY and DATASET_PATH
```

### 3. Add your dataset

Place your CSV, Parquet, or Excel file in the `data/` directory and update
`DATASET_PATH` in `.env`.

### 4. Run the app

```bash
streamlit run app.py
```

### 5. Run tests

```bash
pytest tests/ -v
```

---

## Project status

| Phase | Description | Status |
|---|---|---|
| 0 | Skeleton & contracts | ✅ Complete |
| 1 | Data layer & tool implementation | 🔲 Next |
| 2 | LLM integration & planner | 🔲 Planned |
| 3 | Streamlit UI | 🔲 Planned |
| 4 | Polish & evaluation | 🔲 Planned |

---

## Project structure

```
insight-copilot/
├── app.py                  # Streamlit entry-point
├── agent/
│   ├── state.py            # AgentState TypedDict
│   ├── graph.py            # LangGraph StateGraph wiring
│   ├── planner.py          # Planner node (LLM → AnalysisPlan)
│   ├── router.py           # Router conditional edge (pure Python)
│   └── synthesizer.py      # Synthesizer node (LLM → final answer)
├── tools/
│   ├── data_query.py       # DuckDB SELECT tool
│   ├── metrics.py          # DuckDB aggregation tool
│   ├── trends.py           # DuckDB trend analysis tool
│   └── charts.py           # Plotly chart rendering tool
├── llm/
│   ├── base.py             # BaseLLM abstract interface
│   ├── gemini.py           # Gemini provider
│   └── factory.py          # create_llm() factory
├── models/
│   └── schemas.py          # Pydantic data contracts
├── utils/
│   ├── prompts.py          # Centralised LLM prompts
│   └── data_loader.py      # DuckDB data loading utility
├── data/                   # Dataset files (git-ignored)
├── docs/
│   ├── architecture.md
│   ├── development-plan.md
│   └── decisions.md
└── tests/
    ├── test_graph.py
    ├── test_router.py
    └── test_tools.py
```

---

## Engineering principles

- **LLM for language; Python for numbers** — the LLM never computes dataset values.
- **Explicit over implicit** — the execution plan is visible, not hidden.
- **Deterministic tools** — same input → same output, every time.
- **No secrets in code** — API keys via environment variables only.
- **Testable by default** — every component can be tested without live API calls.

---

## License

MIT — see [`LICENSE`](LICENSE).
