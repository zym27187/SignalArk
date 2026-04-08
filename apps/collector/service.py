"""Collector runtime for historical backfill, live bars, and recovery."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any, Literal, Protocol

import structlog
from src.domain.events import BarEvent
from src.domain.market import FinalBarGate, NormalizedBar
from src.infra.exchanges import EastmoneyAshareBarGateway, FixtureAshareBarGateway

from apps.collector.checkpoints import FileCollectorCheckpointStore


class CollectorCheckpointStore(Protocol):
    """Minimal checkpoint contract required by the collector runtime."""

    def next_start_time(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
    ) -> datetime | None: ...

    def record(self, event: BarEvent) -> None: ...


class MarketBarGateway(Protocol):
    """Minimal bar-gateway contract required by the collector runtime."""

    async def aclose(self) -> None: ...

    async def fetch_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_bars: int | None = None,
    ) -> list[NormalizedBar]: ...

    async def stream_live_bars(
        self,
        symbols: Sequence[str],
        timeframe: str,
    ) -> AsyncIterator[NormalizedBar]: ...


class NullCollectorCheckpointStore:
    """No-op checkpoint store used when persistence is disabled."""

    def next_start_time(self, exchange: str, symbol: str, timeframe: str) -> datetime | None:
        return None

    def record(self, event: BarEvent) -> None:
        return None


class CollectorService:
    """Consume exchange bars and emit only deduplicated final BarEvents."""

    def __init__(
        self,
        gateway: MarketBarGateway,
        *,
        exchange: str,
        symbols: Sequence[str],
        timeframe: str,
        checkpoint_store: CollectorCheckpointStore | None = None,
        history_seed_bars: int = 200,
        reconnect_delay_seconds: float = 2.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._gateway = gateway
        self._exchange = exchange
        self._symbols = tuple(symbols)
        self._timeframe = timeframe
        self._checkpoint_store = checkpoint_store or NullCollectorCheckpointStore()
        self._history_seed_bars = history_seed_bars
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._sleep = sleep
        self._gate = FinalBarGate()
        self._logger = structlog.get_logger(__name__)

    async def aclose(self) -> None:
        """Close resources owned by the underlying exchange gateway."""
        await self._gateway.aclose()

    async def collect_actionable_bars(
        self,
        *,
        max_events: int | None = None,
    ) -> AsyncIterator[BarEvent]:
        """Yield only closed/final bars after bootstrap, dedup, and recovery."""
        emitted = 0

        for event in await self._backfill_with_retry(stage="bootstrap"):
            yield event
            emitted += 1
            if max_events is not None and emitted >= max_events:
                return

        while True:
            try:
                async for bar in self._gateway.stream_live_bars(self._symbols, self._timeframe):
                    event = self._process_bar(bar, stage="live")
                    if event is None:
                        continue

                    yield event
                    emitted += 1
                    if max_events is not None and emitted >= max_events:
                        return
            except Exception as exc:
                self._logger.warning(
                    "collector_stream_disconnected",
                    exchange=self._exchange,
                    timeframe=self._timeframe,
                    symbols=list(self._symbols),
                    error=str(exc),
                )
            else:
                self._logger.warning(
                    "collector_stream_ended",
                    exchange=self._exchange,
                    timeframe=self._timeframe,
                    symbols=list(self._symbols),
                )

            await self._sleep(self._reconnect_delay_seconds)

            for event in await self._backfill_with_retry(stage="recovery"):
                yield event
                emitted += 1
                if max_events is not None and emitted >= max_events:
                    return

    async def _backfill_with_retry(self, *, stage: str) -> list[BarEvent]:
        while True:
            try:
                return await self._backfill(stage=stage)
            except Exception as exc:
                self._logger.warning(
                    "collector_backfill_failed",
                    stage=stage,
                    exchange=self._exchange,
                    timeframe=self._timeframe,
                    symbols=list(self._symbols),
                    error=str(exc),
                )
                await self._sleep(self._reconnect_delay_seconds)

    async def _backfill(self, *, stage: str) -> list[BarEvent]:
        events: list[BarEvent] = []
        for symbol in self._symbols:
            start_time = self._checkpoint_store.next_start_time(
                self._exchange,
                symbol,
                self._timeframe,
            )
            max_bars = self._history_seed_bars if start_time is None else None

            bars = await self._gateway.fetch_historical_bars(
                symbol,
                self._timeframe,
                start_time=start_time,
                max_bars=max_bars,
            )
            for bar in bars:
                event = self._process_bar(bar, stage=stage)
                if event is not None:
                    events.append(event)

        return events

    def _process_bar(self, bar: NormalizedBar, *, stage: str) -> BarEvent | None:
        decision = self._gate.process(bar)
        self._logger.info(
            "collector_bar_processed",
            stage=stage,
            status=decision.status,
            reason=decision.reason,
            bar_key=decision.event.bar_key,
            exchange=decision.event.exchange,
            symbol=decision.event.symbol,
            timeframe=decision.event.timeframe,
            closed=decision.event.closed,
            final=decision.event.final,
            source_kind=decision.event.source_kind,
        )

        if decision.status != "emit":
            return None

        self._checkpoint_store.record(decision.event)
        return decision.event


def build_default_collector_service(
    *,
    exchange: str,
    symbols: Sequence[str],
    timeframe: str,
    market_data_source: Literal["eastmoney", "fixture"] = "eastmoney",
    symbol_rules: dict[str, Any] | None = None,
) -> CollectorService:
    """Build the default collector runtime used by the CLI entrypoint."""
    gateway: MarketBarGateway
    checkpoint_store: CollectorCheckpointStore
    history_seed_bars = 200
    if market_data_source == "fixture":
        gateway = FixtureAshareBarGateway()
        checkpoint_store = NullCollectorCheckpointStore()
        history_seed_bars = 1
    else:
        gateway = EastmoneyAshareBarGateway(symbol_rules=symbol_rules)
        checkpoint_store = FileCollectorCheckpointStore()

    return CollectorService(
        gateway,
        exchange=exchange,
        symbols=symbols,
        timeframe=timeframe,
        checkpoint_store=checkpoint_store,
        history_seed_bars=history_seed_bars,
    )
