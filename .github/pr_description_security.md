## Description
This PR enhances configuration security, secret redaction, and clean deployment isolation:
1. **Enhanced Secret Redaction**: Extends `SensitiveDataFilter` in `utils/logging_config.py` with multi-token regex protection, scrubbing Google AIza keys, `GEMINI_API_KEY` assignments, Bearer authorization tokens, and generic API keys/tokens from both application console streams and rotating log files.
2. **Security Testing**: Adds unit assertions in `tests/test_logging.py` validating redaction across Bearer tokens and generic credentials.
3. **Repository Secret Hygiene**: Verified zero untracked or leaked secrets across codebase and documentation.

## Changes
- `utils/logging_config.py`: Expanded regex pattern suite for `SensitiveDataFilter`.
- `tests/test_logging.py`: Added tests for Bearer and token redaction.

## Verification
- `pytest tests/test_logging.py -v`: 3 passed in 0.07s
- `pytest tests/ --ignore=tests/integration -v`: 172 passed
