"""Local fixture market-data adapter for development and demos."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Literal

from src.domain.market import (
    NormalizedBar,
    SuspensionStatus,
    build_market_state_snapshot,
    timeframe_to_timedelta,
)
from src.shared.types import SHANGHAI_TIMEZONE, shanghai_now

Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]

FIXTURE_BASE_PRICES: dict[str, Decimal] = {
    "600036.SH": Decimal("39.50"),
    "000001.SZ": Decimal("13.20"),
}
FIXTURE_PRICE_TICK = Decimal("0.01")
FIXTURE_PRICE_LIMIT_PCT = Decimal("0.10")
FIXTURE_PREVIOUS_CLOSE_GAP = Decimal("0.05")
FIXTURE_VOLUME = Decimal("1200000")
FIXTURE_SOURCE_NAME = "signalark_fixture_bar"


def _ensure_shanghai(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must be timezone-aware")
    return value.astimezone(SHANGHAI_TIMEZONE)


def _bar_end_for(at: datetime, timeframe: str) -> datetime:
    localized = _ensure_shanghai(at)
    step = timeframe_to_timedelta(timeframe)
    step_seconds = int(step.total_seconds())
    localized_timestamp = int(localized.timestamp())
    return datetime.fromtimestamp(
        localized_timestamp - (localized_timestamp % step_seconds),
        tz=SHANGHAI_TIMEZONE,
    )


def _base_price_for_symbol(symbol: str) -> Decimal:
    normalized = symbol.strip().upper()
    if normalized in FIXTURE_BASE_PRICES:
        return FIXTURE_BASE_PRICES[normalized]

    checksum = sum(ord(char) for char in normalized)
    return Decimal("10") + Decimal(checksum % 30)


class FixtureAshareBarGateway:
    """Generate deterministic recent bars so local trader flows can run without upstream data."""

    def __init__(
        self,
        *,
        poll_interval_seconds: float = 5.0,
        clock: Clock = shanghai_now,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._poll_interval_seconds = poll_interval_seconds
        self._clock = clock
        self._sleep = sleep

    async def aclose(self) -> None:
        return None

    async def fetch_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_bars: int | None = None,
    ) -> list[NormalizedBar]:
        anchor = end_time if end_time is not None else self._clock()
        anchor_end = _bar_end_for(anchor, timeframe)
        step = timeframe_to_timedelta(timeframe)

        if max_bars is not None:
            count = max_bars
        elif start_time is not None:
            start_local = _ensure_shanghai(start_time)
            span = max(anchor_end - start_local, step)
            count = max(1, int(span / step) + 2)
        else:
            count = 200

        count = min(count, 2048)
        bars = [
            self._build_bar(
                symbol=symbol,
                timeframe=timeframe,
                bar_end_time=anchor_end - step * offset,
                source_kind="historical",
            )
            for offset in range(count - 1, -1, -1)
        ]

        if start_time is not None:
            start_local = _ensure_shanghai(start_time)
            bars = [bar for bar in bars if bar.bar_start_time >= start_local]
        if end_time is not None:
            end_local = _ensure_shanghai(end_time)
            bars = [bar for bar in bars if bar.bar_end_time <= end_local]
        if max_bars is not None:
            bars = bars[-max_bars:]

        return bars

    async def stream_live_bars(
        self,
        symbols: Sequence[str],
        timeframe: str,
    ) -> AsyncIterator[NormalizedBar]:
        while True:
            current_time = self._clock()
            bar_end_time = _bar_end_for(current_time, timeframe)
            for symbol in symbols:
                yield self._build_bar(
                    symbol=symbol,
                    timeframe=timeframe,
                    bar_end_time=bar_end_time,
                    source_kind="realtime",
                )

            await self._sleep(self._poll_interval_seconds)

    def _build_bar(
        self,
        *,
        symbol: str,
        timeframe: str,
        bar_end_time: datetime,
        source_kind: Literal["historical", "realtime"],
    ) -> NormalizedBar:
        normalized_symbol = symbol.strip().upper()
        step = timeframe_to_timedelta(timeframe)
        bar_end_local = _ensure_shanghai(bar_end_time)
        bar_start_time = bar_end_local - step
        base_price = _base_price_for_symbol(normalized_symbol)
        sequence_offset = Decimal(int(bar_end_local.timestamp() // step.total_seconds()) % 7) / 100
        close_price = (base_price + sequence_offset).quantize(FIXTURE_PRICE_TICK)
        previous_close = (close_price - FIXTURE_PREVIOUS_CLOSE_GAP).quantize(FIXTURE_PRICE_TICK)
        open_price = previous_close
        high_price = (close_price + Decimal("0.08")).quantize(FIXTURE_PRICE_TICK)
        low_price = (close_price - Decimal("0.07")).quantize(FIXTURE_PRICE_TICK)
        quote_volume = (FIXTURE_VOLUME * close_price).quantize(Decimal("0.01"))
        market_state = build_market_state_snapshot(
            event_time=bar_end_local,
            previous_close=previous_close,
            price_limit_pct=FIXTURE_PRICE_LIMIT_PCT,
            price_tick=FIXTURE_PRICE_TICK,
            suspension_status=SuspensionStatus.ACTIVE,
        )

        return NormalizedBar(
            exchange="cn_equity",
            symbol=normalized_symbol,
            timeframe=timeframe,
            bar_start_time=bar_start_time,
            bar_end_time=bar_end_local,
            ingest_time=self._clock(),
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=FIXTURE_VOLUME,
            quote_volume=quote_volume,
            trade_count=420,
            closed=True,
            final=True,
            source_kind=source_kind,
            market_state=market_state,
            source_payload={
                "source": FIXTURE_SOURCE_NAME,
                "symbol": normalized_symbol,
                "timeframe": timeframe,
                "bar_end_time": bar_end_local.isoformat(),
            },
        )
