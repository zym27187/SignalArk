"""Shared logging setup for JSON-like structured logs."""

from __future__ import annotations

import logging
import sys

import structlog


def clear_log_context() -> None:
    """Reset any request or runtime-scoped logging context."""
    structlog.contextvars.clear_contextvars()


def bind_log_context(**values: object) -> None:
    """Bind non-empty key/value pairs into the current logging context."""
    payload = {key: value for key, value in values.items() if value is not None}
    if payload:
        structlog.contextvars.bind_contextvars(**payload)


def configure_logging(level: str = "INFO", *, service: str | None = None) -> None:
    """Configure stdlib logging and structlog for simple JSON output."""
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            timestamper,
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
