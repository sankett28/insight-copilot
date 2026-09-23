"""
utils/logging_config.py
-----------------------
Persistent application logging configuration with rotating file handler,
safe redaction of secrets, and structured run-level event tracking.
"""

from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"
DEFAULT_LOG_LEVEL = "INFO"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3

# Regex patterns for redacting sensitive secrets
_SECRET_PATTERNS = [
    re.compile(r"(AIza[0-9A-Za-z-_]{35})"),  # Google API key format
    re.compile(r"(GEMINI_API_KEY\s*[:=]\s*['\"]?)([^'\"\s]+)(['\"]?)", re.IGNORECASE),
]


class SensitiveDataFilter(logging.Filter):
    """Logging filter to redact API keys and secrets from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (self.redact(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    (self.redact(a) if isinstance(a, str) else a)
                    for a in record.args
                )
        return True

    @staticmethod
    def redact(text: str) -> str:
        """Redact sensitive patterns in text."""
        res = text
        for pattern in _SECRET_PATTERNS:
            res = pattern.sub("[REDACTED_API_KEY]", res)
        return res



def setup_logging(
    level: str | None = None,
    log_to_file: bool = True,
    log_to_console: bool = True,
    log_file: Path | None = None,
) -> logging.Logger:
    """Configure application-wide root logging with rotating file handler and console handler.

    Args:
        level: Log level (e.g. 'DEBUG', 'INFO', 'WARNING'). Defaults to LOG_LEVEL env var or 'INFO'.
        log_to_file: Whether to attach RotatingFileHandler to logs/app.log.
        log_to_console: Whether to attach StreamHandler to stderr/stdout.
        log_file: Optional custom file path for logs. Defaults to logs/app.log.

    Returns:
        Root logger configured for application execution.
    """
    resolved_level_name = (
        level or os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL)
    ).upper()
    log_level = getattr(logging, resolved_level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    sensitive_filter = SensitiveDataFilter()

    # Avoid duplicate handlers if already configured
    existing_handler_types = {type(h) for h in root_logger.handlers}

    # 1. Console Handler
    if log_to_console and logging.StreamHandler not in existing_handler_types:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(sensitive_filter)
        root_logger.addHandler(console_handler)

    # 2. Rotating File Handler
    target_file = log_file or LOG_FILE
    if log_to_file:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        # Check if file handler for target_file already exists
        has_file_handler = any(
            isinstance(h, RotatingFileHandler)
            and getattr(h, "baseFilename", None) == str(target_file.resolve())
            for h in root_logger.handlers
        )
        if not has_file_handler:
            file_handler = RotatingFileHandler(
                filename=str(target_file),
                maxBytes=MAX_BYTES,
                backupCount=BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(sensitive_filter)
            root_logger.addHandler(file_handler)

    return root_logger



# ---------------------------------------------------------------------------
# Structured Run Event Helpers
# ---------------------------------------------------------------------------

_app_logger = logging.getLogger("insight_copilot.execution")


def log_run_start(run_id: str, query: str) -> None:
    """Log the beginning of a user query execution turn."""
    # Truncate long queries in summary log
    safe_query = query.strip().replace("\n", " ")
    if len(safe_query) > 100:
        safe_query = safe_query[:97] + "..."
    _app_logger.info("[run=%s] query start: '%s'", run_id, safe_query)


def log_planner_completed(
    run_id: str,
    intent: str,
    tools: list[str],
    latency_ms: float,
) -> None:
    """Log completion of planner node."""
    tools_str = ",".join(tools) if tools else "none"
    _app_logger.info(
        "[run=%s] planner completed intent=%s tools=[%s] latency=%.0fms",
        run_id,
        intent,
        tools_str,
        latency_ms,
    )


def log_tool_executed(
    run_id: str,
    tool_name: str,
    step: int,
    success: bool,
    latency_ms: float,
    error: str | None = None,
) -> None:
    """Log individual tool execution outcome."""
    status_str = "true" if success else "false"
    err_context = f" error='{error}'" if error else ""
    _app_logger.info(
        "[run=%s] tool=%s step=%d success=%s latency=%.0fms%s",
        run_id,
        tool_name,
        step,
        status_str,
        latency_ms,
        err_context,
    )


def log_dependency_blocked(
    run_id: str,
    step: int,
    required_step: int,
) -> None:
    """Log dependency gate block."""
    _app_logger.warning(
        "[run=%s] dependency blocked step=%d required_step=%d",
        run_id,
        step,
        required_step,
    )


def log_synthesis_completed(
    run_id: str,
    latency_ms: float,
) -> None:
    """Log completion of synthesizer node."""
    _app_logger.info(
        "[run=%s] synthesis completed latency=%.0fms",
        run_id,
        latency_ms,
    )


def log_graph_completed(
    run_id: str,
    success: bool,
    total_latency_ms: float,
) -> None:
    """Log end-to-end graph completion or failure."""
    if success:
        _app_logger.info(
            "[run=%s] graph completed latency=%.0fms",
            run_id,
            total_latency_ms,
        )
    else:
        _app_logger.error(
            "[run=%s] graph failed latency=%.0fms",
            run_id,
            total_latency_ms,
        )
