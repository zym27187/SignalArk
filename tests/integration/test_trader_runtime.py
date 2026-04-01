from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from apps.trader.service import TraderEventContext, TraderPipelinePorts, TraderService
from src.domain.events import BarEvent

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 3, 31, 14, 15, tzinfo=SHANGHAI)


def _bar_event(
    *,
    offset_minutes: int,
    closed: bool,
    final: bool,
    source_kind: str,
) -> BarEvent:
    bar_start = BASE_TIME + timedelta(minutes=offset_minutes)
    bar_end = bar_start + timedelta(minutes=15)
    return BarEvent(
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        bar_start_time=bar_start,
        bar_end_time=bar_end,
        event_time=bar_end,
        ingest_time=bar_end + timedelta(seconds=2),
        open=Decimal("39.40"),
        high=Decimal("39.55"),
        low=Decimal("39.38"),
        close=Decimal("39.50"),
        volume=Decimal("1000"),
        closed=closed,
        final=final,
        source_kind=source_kind,
    )


class SequenceEventSource:
    def __init__(self, events: Sequence[object]) -> None:
        self._events = list(events)
        self.closed = False

    def events(self) -> AsyncIterator[object]:
        async def _iterator() -> AsyncIterator[object]:
            for event in self._events:
                yield event

        return _iterator()

    async def aclose(self) -> None:
        self.closed = True


class BlockingEventSource:
    def __init__(self) -> None:
        self._released = asyncio.Event()
        self.closed = False

    def events(self) -> AsyncIterator[object]:
        async def _iterator() -> AsyncIterator[object]:
            await self._released.wait()
            if False:
                yield  # pragma: no cover

        return _iterator()

    async def aclose(self) -> None:
        self.closed = True
        self._released.set()


class RecordingStrategy:
    def __init__(self) -> None:
        self.events: list[BarEvent] = []
        self.contexts: list[TraderEventContext] = []

    async def on_bar(self, event: BarEvent, context: TraderEventContext) -> None:
        self.events.append(event)
        self.contexts.append(context)


@pytest.mark.asyncio
async def test_trader_runtime_routes_only_unique_final_bars_to_strategy() -> None:
    strategy = RecordingStrategy()
    source = SequenceEventSource(
        [
            _bar_event(offset_minutes=0, closed=False, final=False, source_kind="realtime"),
            _bar_event(offset_minutes=0, closed=True, final=True, source_kind="historical"),
            _bar_event(offset_minutes=0, closed=True, final=True, source_kind="realtime"),
            _bar_event(offset_minutes=15, closed=True, final=True, source_kind="realtime"),
        ]
    )
    trader = TraderService(
        source,
        pipeline=TraderPipelinePorts(strategy=strategy),
    )

    await trader.run()

    assert [event.bar_key for event in strategy.events] == [
        "cn_equity:600036.SH:15m:2026-03-31T14:15:00+08:00",
        "cn_equity:600036.SH:15m:2026-03-31T14:30:00+08:00",
    ]
    assert len(strategy.contexts) == 2
    assert all(
        context.trader_run_id == trader.runtime_state.trader_run_id for context in strategy.contexts
    )
    assert all(
        context.instance_id == trader.runtime_state.instance_id for context in strategy.contexts
    )
    assert source.closed is True

    snapshot = trader.runtime_snapshot()
    assert snapshot["status"] == "stopped"
    assert snapshot["stop_reason"] == "source_exhausted"
    assert snapshot["last_strategy_bar_key"] == "cn_equity:600036.SH:15m:2026-03-31T14:30:00+08:00"
    assert snapshot["last_ignored_bar_reason"] == "bar_key_already_triggered"
    assert snapshot["pipeline"]["strategy"]["status"] == "bound"
    assert snapshot["pipeline"]["risk"]["status"] == "reserved"
    assert snapshot["pipeline"]["oms"]["status"] == "reserved"


@pytest.mark.asyncio
async def test_trader_runtime_exposes_start_stop_lifecycle_and_health_views() -> None:
    source = BlockingEventSource()
    trader = TraderService(source)

    await trader.start()

    assert trader.runtime_state.status == "running"
    assert trader.health_payload()["status"] == "alive"
    assert trader.readiness_payload()["status"] == "ready"
    assert trader.readiness_payload()["single_active"]["status"] == "unbound"

    await trader.stop(reason="test_shutdown")

    assert source.closed is True
    assert trader.runtime_state.status == "stopped"
    assert trader.runtime_state.stop_reason == "test_shutdown"
    assert trader.health_payload()["status"] == "stopped"
    assert trader.readiness_payload()["status"] == "not_ready"
