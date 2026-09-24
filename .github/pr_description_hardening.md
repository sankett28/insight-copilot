## Description
This PR addresses critical release hardening items for Phase 4 deployment readiness:
1. **Dataset Bundling**: Whitelists and tracks the canonical enterprise dataset `data/Sales_Dataset_2024.xlsx` so fresh repository clones and cloud deployments (Streamlit Cloud, Docker) initialize with real analytical data out of the box without `FileNotFoundError`.
2. **Runtime Dependencies**: Adds `openpyxl>=3.1.0` to `requirements.txt` to support Excel data ingestion via `pandas.read_excel()` during dataset initialization.
3. **Environment Configuration**: Updates `.env.example` with standard defaults (`DATASET_PATH=data/Sales_Dataset_2024.xlsx`, `LOG_LEVEL=INFO`).
4. **Automated Evaluation Baseline**: Captures verified evaluation results across 35 benchmark cases with 100% accuracy.

## Changes
- `.gitignore`: Whitelist `!data/Sales_Dataset_2024.xlsx` while maintaining ignores for raw derived artifacts.
- `requirements.txt`: Added `openpyxl>=3.1.0`.
- `.env.example`: Updated default configuration paths.
- `data/Sales_Dataset_2024.xlsx`: Added canonical dataset.
- `docs/evaluation-results.md`: Updated baseline benchmark execution report.

## Verification
- `pytest tests/ --ignore=tests/integration -v`: 168 passed in 14.5s
- `python tests/evaluation/run_eval.py`: 35/35 benchmark cases passed (100.0%)
- `python scripts/acceptance_test_runner.py`: 25/25 acceptance tests passed (100.0%)
