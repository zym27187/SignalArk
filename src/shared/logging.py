"""Shared logging setup for JSON-like structured logs."""

from __future__ import annotations

import logging
import sys

import structlog

from src.shared.types import shanghai_now


def clear_log_context() -> None:
    """Reset any request or runtime-scoped logging context."""
    structlog.contextvars.clear_contextvars()


def bind_log_context(**values: object) -> None:
    """Bind non-empty key/value pairs into the current logging context."""
    payload = {key: value for key, value in values.items() if value is not None}
    if payload:
        structlog.contextvars.bind_contextvars(**payload)


def _add_shanghai_timestamp(_: object, __: str, event_dict: dict[str, object]) -> dict[str, object]:
    """Attach an Asia/Shanghai timestamp to every structured log event."""
    event_dict.setdefault("timestamp", shanghai_now().isoformat())
    return event_dict


def configure_logging(level: str = "INFO", *, service: str | None = None) -> None:
    """Configure stdlib logging and structlog for simple JSON output."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_shanghai_timestamp,
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    clear_log_context()
    if service is not None:
        bind_log_context(service=service)
