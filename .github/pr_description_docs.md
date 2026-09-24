## Description
This PR reconciles all project documentation across the repository to accurately match the Phase 4 Release Candidate state:
1. **`README.md`**: Updated regression test counts (172 tests), quickstart commands, and links to all architectural records.
2. **`docs/architecture.md`**: Reconciled system overview, component matrix, Mermaid DAG flows, and capability registry specifications to reflect all 13 active analytical capabilities and the `google-genai` SDK.
3. **`docs/decisions.md`**: Added ADR-011 (Two-Tier Bronze/Silver Data Layer & Dimension Hygiene Isolation) and reconciled all ADRs 1–11.
4. **`docs/development-plan.md`**: Marked Phase 0 through Phase 4 complete, recording 100% pass rates across the 35-case benchmark and 25-case acceptance suite.
5. **`data/README.md`**: Documented canonical dataset `Sales_Dataset_2024.xlsx` (2,000 rows, 10 columns), schema semantics, and Bronze/Silver data layer behavior.

## Changes
- `README.md`: Updated architecture summary, test counts, and documentation index.
- `docs/architecture.md`: Reconciled architecture diagram, components, and capability registry.
- `docs/decisions.md`: Added ADR-011.
- `docs/development-plan.md`: Reconciled roadmap and marked Phase 4 complete.
- `data/README.md`: Documented canonical dataset and data layers.

## Verification
- Cross-checked all documented tool names, schemas, counts, and test numbers against runtime code.
- `pytest tests/ --ignore=tests/integration -v`: 172 passed
