"""Structured logging via structlog, with secret redaction."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

_SECRET_KEYS = re.compile(r"(api[_-]?key|secret|token|password|authorization)", re.IGNORECASE)
_SECRET_VALUE = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{10,}|gsk_[A-Za-z0-9_-]{8,})")


def _redact(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key, value in list(event_dict.items()):
        if _SECRET_KEYS.search(key):
            event_dict[key] = "***"
        elif isinstance(value, str) and _SECRET_VALUE.search(value):
            event_dict[key] = _SECRET_VALUE.sub("***", value)
    return event_dict


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    logging.basicConfig(stream=sys.stdout, level=level.upper(), format="%(message)s")
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    renderer: Any = (
        structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer(colors=True)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "app") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
