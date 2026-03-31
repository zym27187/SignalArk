"""Collector runtime entrypoint."""

from __future__ import annotations

import asyncio

import structlog
from src.config import get_settings
from src.shared.logging import configure_logging

from apps.collector.service import build_default_collector_service


async def _run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, service="collector")
    logger = structlog.get_logger(__name__)

    collector = build_default_collector_service(
        exchange=settings.exchange,
        symbols=settings.symbols,
        timeframe=settings.primary_timeframe,
        symbol_rules=settings.symbol_rules,
    )

    logger.info(
        "collector_started",
        env=settings.env,
        exchange=settings.exchange,
        symbols=settings.symbols,
        timeframe=settings.primary_timeframe,
    )

    try:
        async for event in collector.collect_actionable_bars():
            logger.info(
                "collector_bar_emitted",
                bar_key=event.bar_key,
                exchange=event.exchange,
                symbol=event.symbol,
                timeframe=event.timeframe,
                bar_start_time=event.bar_start_time.isoformat(),
                bar_end_time=event.bar_end_time.isoformat(),
                source_kind=event.source_kind,
            )
    finally:
        await collector.aclose()


def main() -> None:
    """Run the collector until interrupted."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
