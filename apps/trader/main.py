"""Trader scaffold entrypoint."""

from __future__ import annotations

import uuid

import structlog
from src.config import get_settings
from src.shared.logging import bind_log_context, configure_logging
from src.shared.types import shanghai_now


def main() -> None:
    """Print a scaffold startup message for the trader runtime."""
    settings = get_settings()
    trader_run_id = str(uuid.uuid4())

    configure_logging(settings.log_level, service="trader")
    if settings.trader_run_id_bind_to_logs:
        bind_log_context(trader_run_id=trader_run_id)

    logger = structlog.get_logger("signalark.trader")

    logger.info(
        "trader_starting",
        env=settings.env,
        execution_mode=settings.execution_mode,
        exchange=settings.exchange,
        symbols=settings.symbols,
        started_at=shanghai_now().isoformat(),
        note="Implement event loop and OMS wiring in Phase 4 and Phase 5.",
    )


if __name__ == "__main__":
    main()
