"""structlog JSON logging to stdout and a daily JSONL file."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog


def setup_logging(log_dir: str | Path = "data/logs", level: str = "INFO") -> Path:
    """Configure structlog for JSON lines to stdout + a daily-rotating file.

    Returns the log file path that was opened.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    file_path = log_path / f"radar-{today}.jsonl"

    file_handler = logging.FileHandler(file_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(message)s"))

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    stdout_handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(file_handler)
    root.addHandler(stdout_handler)

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    return file_path


def get_logger(name: str = "radar"):
    return structlog.get_logger(name)
