from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from src.domain.events import BarEvent
from src.infra.messaging import InProcessEventBus

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 3, 31, 14, 15, tzinfo=SHANGHAI)


def _bar_event(*, offset_minutes: int) -> BarEvent:
    bar_start = BASE_TIME + timedelta(minutes=offset_minutes)
    bar_end = bar_start + timedelta(minutes=15)
    return BarEvent(
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        bar_start_time=bar_start,
        bar_end_time=bar_end,
        event_time=bar_end,
        ingest_time=bar_end + timedelta(seconds=1),
        open=Decimal("39.40"),
        high=Decimal("39.55"),
        low=Decimal("39.38"),
        close=Decimal("39.50"),
        volume=Decimal("1000"),
        closed=True,
        final=True,
        source_kind="historical",
    )


@pytest.mark.asyncio
async def test_in_process_event_bus_dispatches_matching_events_in_publish_order() -> None:
    bus = InProcessEventBus()
    seen: list[str] = []

    async def handle_bar(event: object) -> None:
        assert isinstance(event, BarEvent)
        seen.append(event.bar_key)

    bus.subscribe(BarEvent, handle_bar, name="test.bar_handler")
    await bus.start()

    try:
        await bus.publish(_bar_event(offset_minutes=0))
        await bus.publish(_bar_event(offset_minutes=15))
    finally:
        await bus.stop()

    assert seen == [
        "cn_equity:600036.SH:15m:2026-03-31T14:15:00+08:00",
        "cn_equity:600036.SH:15m:2026-03-31T14:30:00+08:00",
    ]


@pytest.mark.asyncio
async def test_in_process_event_bus_unsubscribe_prevents_future_delivery() -> None:
    bus = InProcessEventBus()
    deliveries: list[str] = []

    delivered_first = asyncio.Event()

    async def handle_bar(event: object) -> None:
        assert isinstance(event, BarEvent)
        deliveries.append(event.bar_key)
        delivered_first.set()

    subscription = bus.subscribe(BarEvent, handle_bar, name="test.unsubscribe")
    await bus.start()

    try:
        await bus.publish(_bar_event(offset_minutes=0))
        await delivered_first.wait()
        bus.unsubscribe(subscription)
        await bus.publish(_bar_event(offset_minutes=15))
    finally:
        await bus.stop()

    assert deliveries == ["cn_equity:600036.SH:15m:2026-03-31T14:15:00+08:00"]
