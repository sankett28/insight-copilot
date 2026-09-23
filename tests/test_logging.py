"""
tests/test_logging.py
---------------------
Unit tests for utils/logging_config.py: rotating file configuration,
sensitive secret redaction, and structured run-level logging helpers.
"""

import logging
from pathlib import Path
import pytest

from utils.logging_config import (
    SensitiveDataFilter,
    setup_logging,
    log_run_start,
    log_planner_completed,
    log_tool_executed,
    log_dependency_blocked,
    log_synthesis_completed,
    log_graph_completed,
    LOG_FILE,
)


def test_sensitive_data_filter_redacts_api_keys():
    """Verify SensitiveDataFilter redacts Gemini API keys and secrets."""
    filter_obj = SensitiveDataFilter()

    # Google AIza key pattern
    fake_key = "AIzaSyD-1234567890abcdefghijklmnopqrstuv"
    raw_msg = f"Initialized GeminiClient with key={fake_key}"
    redacted = filter_obj.redact(raw_msg)
    assert fake_key not in redacted
    assert "[REDACTED_API_KEY]" in redacted

    # GEMINI_API_KEY assignment pattern
    raw_env_msg = "Configured environment GEMINI_API_KEY=my_secret_token_123"
    redacted_env = filter_obj.redact(raw_env_msg)
    assert "my_secret_token_123" not in redacted_env
    assert "[REDACTED_API_KEY]" in redacted_env


def test_sensitive_data_filter_logging_record():
    """Verify filter modifies LogRecord in-place."""
    filter_obj = SensitiveDataFilter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="API Key is AIzaSyD-1234567890abcdefghijklmnopqrstuv",
        args=(),
        exc_info=None,
    )
    filter_obj.filter(record)
    assert "AIzaSyD" not in record.msg
    assert "[REDACTED_API_KEY]" in record.msg


def test_setup_logging_creates_log_file(tmp_path):
    """Verify setup_logging attaches RotatingFileHandler and writes to log file."""
    custom_log = tmp_path / "test_app.log"
    root_logger = setup_logging(
        level="DEBUG",
        log_to_file=True,
        log_to_console=False,
        log_file=custom_log,
    )
    assert root_logger.level == logging.DEBUG

    test_run_id = "test_run_12345"
    log_run_start(test_run_id, "What is the total revenue by region?")
    log_planner_completed(test_run_id, "metrics", ["metrics", "charts"], 150.0)
    log_tool_executed(test_run_id, "metrics", 1, True, 25.0)
    log_dependency_blocked(test_run_id, 2, 1)
    log_synthesis_completed(test_run_id, 300.0)
    log_graph_completed(test_run_id, True, 475.0)

    # Force flush handlers
    for handler in root_logger.handlers:
        handler.flush()

    assert custom_log.exists()
    content = custom_log.read_text(encoding="utf-8")
    assert f"[run={test_run_id}]" in content
    assert "planner completed intent=metrics tools=[metrics,charts] latency=150ms" in content
    assert "tool=metrics step=1 success=true latency=25ms" in content
    assert "dependency blocked step=2 required_step=1" in content
    assert "synthesis completed latency=300ms" in content
    assert "graph completed latency=475ms" in content

