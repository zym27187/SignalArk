"""Trader runtime entrypoint."""

from __future__ import annotations

import asyncio

import structlog
from src.config import get_settings
from src.shared.logging import bind_log_context, configure_logging

from apps.trader.service import build_default_trader_service


async def _run() -> None:
    """Run the trader runtime until interrupted or its source ends."""
    settings = get_settings()
    trader = build_default_trader_service(settings)
    trader_run_id = trader.runtime_state.trader_run_id

    configure_logging(settings.log_level, service="trader")
    if settings.trader_run_id_bind_to_logs:
        bind_log_context(
            trader_run_id=trader_run_id,
            trader_instance_id=trader.runtime_state.instance_id,
        )

    logger = structlog.get_logger("signalark.trader")

    logger.info(
        "trader_bootstrap_prepared",
        env=settings.env,
        execution_mode=settings.execution_mode,
        exchange=settings.exchange,
        symbols=settings.symbols,
        timeframe=settings.primary_timeframe,
        trader_run_id=trader_run_id,
        trader_run_id_generation=settings.trader_run_id_generation,
        note="Phase 4 trader runtime uses an in-process event bus and awaits strategy wiring.",
    )
    await trader.run()


def main() -> None:
    """Run the trader until interrupted."""
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
