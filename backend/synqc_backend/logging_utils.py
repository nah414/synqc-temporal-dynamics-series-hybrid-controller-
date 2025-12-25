from __future__ import annotations

"""Structured JSON logging helpers with request-scoped context."""

import json
import logging
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict


# Context propagated into every log line.
_CONTEXT: logging.LoggerAdapter | None = None


def _context_vars() -> Dict[str, object]:
    if _CONTEXT is None:
        return {}
    data = getattr(_CONTEXT, "extra", {}) or {}
    return dict(data)


class ContextAwareAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        context = dict(self.extra)
        record_extra = kwargs.get("extra") or {}
        context.update(record_extra)
        kwargs["extra"] = context
        return msg, kwargs


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - logging override
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge contextual extras (request/session/run identifiers, etc.).
        for key, value in record.__dict__.items():
            if key in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
            }:
                continue
            if key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def configure_json_logging(level: int = logging.INFO) -> None:
    """Route application logs through a JSON formatter with contextual extras."""

    global _CONTEXT
    base_logger = logging.getLogger()
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    base_logger.handlers = [handler]
    base_logger.setLevel(level)

    # Wrap the root logger so downstream modules inherit contextual extras.
    _CONTEXT = ContextAwareAdapter(base_logger, extra={})


def set_log_context(**fields: object) -> None:
    """Update the shared logging context for subsequent log lines."""

    global _CONTEXT
    if _CONTEXT is None:
        _CONTEXT = ContextAwareAdapter(logging.getLogger(), extra={})

    extras = getattr(_CONTEXT, "extra", {}) or {}
    extras.update({k: v for k, v in fields.items() if v is not None})
    _CONTEXT.extra = extras


@contextmanager
def log_context(**fields: object):
    """Temporarily push contextual fields (request_id, session_id, etc.)."""

    if _CONTEXT is None:
        configure_json_logging()
    adapter = _CONTEXT  # type: ignore[misc]
    prev = dict(adapter.extra or {})
    set_log_context(**fields)
    try:
        yield
    finally:
        adapter.extra = prev


def get_logger(name: str) -> logging.LoggerAdapter:
    if _CONTEXT is None:
        configure_json_logging()
    assert _CONTEXT is not None
    return ContextAwareAdapter(logging.getLogger(name), extra=dict(_CONTEXT.extra))

