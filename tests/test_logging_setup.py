"""Logging configuration."""

from __future__ import annotations

import json
import logging

from portpulse.logging_setup import JsonFormatter, configure_logging


def _record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="portpulse.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="planning %s vessels",
        args=(3,),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emits_one_parseable_object() -> None:
    payload = json.loads(JsonFormatter().format(_record()))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "portpulse.test"
    assert payload["message"] == "planning 3 vessels"
    assert payload["timestamp"].endswith("+00:00")


def test_json_formatter_preserves_structured_extras() -> None:
    payload = json.loads(JsonFormatter().format(_record(request_id="abc123")))
    assert payload["request_id"] == "abc123"


def test_json_formatter_includes_exception_text() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _record()
        record.exc_info = sys.exc_info()

    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in payload["exception"]


def test_configure_logging_sets_the_root_level() -> None:
    try:
        configure_logging("WARNING")
        assert logging.getLogger().level == logging.WARNING
        configure_logging("DEBUG", json_output=True)
        assert logging.getLogger().level == logging.DEBUG
    finally:
        configure_logging("WARNING")
