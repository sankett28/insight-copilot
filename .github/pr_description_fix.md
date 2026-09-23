# PR Description: Fix Live Testing Reliability, SQL Filter Builder, and Persistent Logging

## Summary of Changes
This pull request addresses concrete runtime issues and determinism defects discovered during live testing of Insight Copilot:

1. **Persistent Application Logging (`utils/logging_config.py`)**:
   - Implemented standard rotating file handler logging to `logs/app.log` (5MB max per file, 3 backups) alongside configurable console output.
   - Built `SensitiveDataFilter` to redact API keys and secrets (`AIza...`, `sk-...`, bearer tokens, `api_key=...`) from log messages and formatting arguments without crashing format specifiers.
   - Added structured lifecycle loggers for execution tracking: `log_run_start`, `log_planner_completed`, `log_tool_executed`, `log_dependency_blocked`, `log_synthesis_completed`, `log_graph_completed`.
   - Integrated into `agent/planner.py`, `agent/router.py`, `agent/synthesizer.py`, `agent/graph.py`, and `app.py`.

2. **Metrics Multi-Value List Filter SQL Builder (`utils/data_loader.py`)**:
   - Fixed DuckDB `VARCHAR` vs `VARCHAR[]` type mismatch bug in SQL generation where list filters previously triggered syntax/type errors.
   - Implemented `build_sql_where_clause` supporting scalar strings (`LOWER(col) = LOWER(...)`), numeric values, and lists (`LOWER(col) IN (...)`), with single-quote escaping and empty list fallback (`1=0`).
   - Integrated into `calculate_all_metrics` and `calculate_metrics_cached`.

3. **Data Cleaning Audit Reconciliation (`utils/data_cleaner.py`)**:
   - Fixed count discrepancy where `nulls_replaced` reported full null counts even when `fill_nulls` was omitted from requested cleaning operations.
   - Ensured exact reconciliation: `raw_null_count -> nulls_replaced -> target_null_count`.

4. **Fuzzy Canonicalization Typo Handling (`utils/data_cleaner.py`)**:
   - Implemented Damerau-Levenshtein distance algorithm to correctly handle adjacent character transpositions (e.g., `MOBLIE` $\to$ `Mobile` edit distance = 1).
   - Enforced frequency dominance and deterministic tie-breaking for cluster centroids.

5. **Synthesizer Data Cleaning Grounding (`utils/prompts.py`)**:
   - Added Rule 6 to `SYNTHESIZER_SYSTEM_PROMPT` to enforce strict grounding in structured cleaning audit results, preventing overclaiming of unperformed operations.

6. **Streamlit Deprecation Fix (`app.py`)**:
   - Replaced deprecated `use_container_width=True/False` with `width="stretch"` / `width="content"`.

---

## Test Results
- **Pytest Suite**: 185 tests passed in 265.63s (0 failures, 0 regressions).
- **New Unit Tests**:
  - `tests/test_logging.py`: Secret redaction, structured event formats, rotating file handler.
  - `tests/test_data_loader.py`: SQL where clause generation for lists, scalars, numerics, empty lists, quote escaping.
  - `tests/test_metrics.py`: Metrics list filter execution in DuckDB.
  - `tests/test_data_clean.py`: Damerau-Levenshtein transposition, `MOBLIE -> Mobile` canonicalization, audit reconciliation.
- **Live User Query Verification**:
  - Executed query: `"Show me all the distinct values in the Region column and how many records each value has."`
  - Output: Successfully generated metrics tool execution with exact value breakdown (`[Step 1]` citations) and complete logs in `logs/app.log`.
