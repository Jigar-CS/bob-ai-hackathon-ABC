"""Logging configuration.

Uses ``dictConfig`` rather than ``basicConfig`` so the configuration is applied
once, explicitly, and does not fight uvicorn's own handlers. JSON output can be
enabled with ``PORTPULSE_LOG_JSON=true`` for log aggregators.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import logging.config
from typing import Any

_CONSOLE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

_RESERVED_RECORD_KEYS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Minimal structured formatter — one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": dt.datetime.fromtimestamp(record.created, tz=dt.timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Preserve any structured extras passed via logger.info(..., extra={...}).
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_KEYS and not key.startswith("_"):
                payload[key] = value

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", *, json_output: bool = False) -> None:
    """Configure root logging for the process. Safe to call more than once."""
    formatter = "json" if json_output else "console"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "console": {"format": _CONSOLE_FORMAT, "datefmt": _DATE_FORMAT},
                "json": {"()": f"{__name__}.JsonFormatter"},
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": formatter,
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {"handlers": ["default"], "level": level},
            "loggers": {
                # uvicorn ships its own handlers; route them through ours instead.
                "uvicorn": {"handlers": ["default"], "level": level, "propagate": False},
                "uvicorn.error": {"handlers": ["default"], "level": level, "propagate": False},
                # RequestContextMiddleware already emits an access line with timing
                # and a correlation ID, so uvicorn's own access log is redundant.
                "uvicorn.access": {"handlers": ["default"], "level": "WARNING", "propagate": False},
                # Third-party noise.
                "urllib3": {"level": "WARNING"},
            },
        }
    )
