"""
app/core/logging.py
───────────────────────────────────────────────────────────────────────────────
Structured application logging.

Provides:
  • configure_logging() — call once at startup (from main.py's lifespan) to
    configure the root logger with either:
      - human-readable console format (development), or
      - JSON line format (production, easy to ingest into log aggregators
        such as ELK / CloudWatch / Datadog)
  • get_logger(name) — factory used by every other module, mirroring the
    `from app.core.logging import get_logger; log = get_logger(__name__)`
    pattern from the desktop application's utils/logger.py.

The log level and JSON/console format are controlled by Settings.LOG_LEVEL
and Settings.LOG_JSON (app/core/config.py).
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _JSONFormatter(logging.Formatter):
    """
    Render log records as single-line JSON objects.

    Useful in production so log aggregators can parse fields (timestamp,
    level, logger name, message, and any extra context) without regex.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Allow callers to attach structured context via `extra={...}`
        for key, value in record.__dict__.items():
            if key.startswith("ctx_"):
                payload[key.removeprefix("ctx_")] = value

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """
    Configure the root logger.

    Called once during application startup (see main.py lifespan).
    Idempotent: clears any existing handlers before reconfiguring, so it
    is safe to call multiple times (e.g. in tests).
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    # Remove pre-existing handlers (e.g. uvicorn defaults) to avoid duplicates
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)

    if settings.LOG_JSON:
        handler.setFormatter(_JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root.addHandler(handler)

    # Tame noisy third-party loggers in development
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG else logging.WARNING
    )


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger.

    Usage:
        from app.core.logging import get_logger
        log = get_logger(__name__)
        log.info("Student registered", extra={"ctx_student_id": student_id})
    """
    return logging.getLogger(name)
