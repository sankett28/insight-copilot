# PR Description: Modern Sticky Split-Screen UI, Step Progress Tracker, and Automated Acceptance Runner

## Summary of Changes

### 1. Modern Split-Screen Streamlit UI (`app.py`)
- **Sticky Execution Trace Column**: Fixed layout scrolling by applying sticky positioning (`position: sticky; max-height: calc(100vh - 4rem); overflow-y: auto`). The conversation pane and trace pane scroll independently without the trace panel disappearing off-screen.
- **Active Prompt & Step Progression Tracker**: Added an active query card featuring:
  - Query text and intent classification badge
  - Total turn execution time (`ms`)
  - Execution status pill (`✅ COMPLETED` / `⚠️ ISSUES`)
  - Visual step timeline pills (e.g., `Step 1: data_clean` $\to$ `Step 2: metrics` $\to$ `Step 3: charts`).
- **Multi-Turn Trace Inspector**: Added persistent turn snapshot history and a turn selector dropdown (`🔍 Inspect Turn History`), allowing users to audit plans, parameters, SQL queries, and tool results from any past conversation turn.
- **Organized Tabbed Trace**:
  - `🗺️ Analytical Plan`: Intent, rationale, and step parameters.
  - `📊 Tool Outputs & SQL`: Structured outputs, formatted SQL blocks, and metric cards.
  - `⏱️ Telemetry & Logs`: Latency breakdowns and recent `logs/app.log` entries.

### 2. Automated Acceptance Test Runner (`scripts/acceptance_test_runner.py`)
- Automated runner for the 25-case Compact Must-Pass Test Pack covering Data Cleaning (DC-01..07), Analytical Correctness (AC-01..09), Multi-Turn Context (MT-01..03), and Unsupported Questions (U-01..06).
- Enforces rate-limiting pacing (7s cooldown) to prevent API quota throttling.
- Captures telemetry and outputs structured results to `logs/acceptance_test_results.json`.

---

## Verification & Testing
- Automated test suite execution: **25/25 passed (100% success rate)** via `scripts/acceptance_test_runner.py`.
- Pytest suite: **185 passed**.
- Verified Streamlit syntax and runtime behavior.
