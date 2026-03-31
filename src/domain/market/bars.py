"""Canonical market bar normalization and gating helpers."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from pydantic import Field, computed_field

from src.domain.events import BarEvent
from src.domain.market.state import MarketStateSnapshot
from src.shared.types import (
    DomainModel,
    NonNegativeDecimal,
    PositiveDecimal,
    ShanghaiDateTime,
    TimeframeStr,
    shanghai_now,
)

BarSourceKind = Literal["historical", "realtime"]


def _normalize_exchange(exchange: str) -> str:
    return exchange.strip().lower()


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _normalize_timeframe(timeframe: str) -> str:
    return timeframe.strip().lower()


def timeframe_to_timedelta(timeframe: str) -> timedelta:
    """Convert timeframe identifiers like 15m / 1h into timedelta objects."""
    normalized = _normalize_timeframe(timeframe)
    if len(normalized) < 2:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}")

    unit = normalized[-1]
    try:
        quantity = int(normalized[:-1])
    except ValueError as exc:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}") from exc

    if quantity <= 0:
        raise ValueError("timeframe quantity must be positive")

    if unit == "m":
        return timedelta(minutes=quantity)
    if unit == "h":
        return timedelta(hours=quantity)
    if unit == "d":
        return timedelta(days=quantity)
    if unit == "w":
        return timedelta(weeks=quantity)

    raise ValueError(f"Unsupported timeframe: {timeframe!r}")


def build_bar_stream_key(exchange: str, symbol: str, timeframe: str) -> str:
    """Return the stable per-stream key used for checkpoints and caches."""
    return ":".join(
        [
            _normalize_exchange(exchange),
            _normalize_symbol(symbol),
            _normalize_timeframe(timeframe),
        ]
    )


def build_bar_key(
    exchange: str,
    symbol: str,
    timeframe: str,
    bar_start_time: datetime,
) -> str:
    """Return the stable final-bar identity for deduplication."""
    return ":".join(
        [
            _normalize_exchange(exchange),
            _normalize_symbol(symbol),
            _normalize_timeframe(timeframe),
            bar_start_time.isoformat(),
        ]
    )


class NormalizedBar(DomainModel):
    """Exchange-agnostic normalized bar prior to collector emission."""

    exchange: str
    symbol: str
    timeframe: TimeframeStr

    bar_start_time: ShanghaiDateTime
    bar_end_time: ShanghaiDateTime
    ingest_time: ShanghaiDateTime = Field(default_factory=shanghai_now)

    open: PositiveDecimal
    high: PositiveDecimal
    low: PositiveDecimal
    close: PositiveDecimal
    volume: NonNegativeDecimal
    quote_volume: NonNegativeDecimal | None = None
    trade_count: int | None = Field(default=None, ge=0)

    closed: bool = False
    final: bool = False
    source_kind: BarSourceKind
    market_state: MarketStateSnapshot | None = None
    source_payload: dict[str, Any] = Field(default_factory=dict)

    @computed_field(return_type=str)
    @property
    def bar_key(self) -> str:
        """Return the stable final-bar identity shared with BarEvent."""
        return build_bar_key(
            self.exchange,
            self.symbol,
            self.timeframe,
            self.bar_start_time,
        )

    @computed_field(return_type=str)
    @property
    def stream_key(self) -> str:
        """Return the stable stream identity for checkpoints and caches."""
        return build_bar_stream_key(self.exchange, self.symbol, self.timeframe)

    @property
    def actionable(self) -> bool:
        """Only closed/final bars may advance into the tradable event chain."""
        return self.closed and self.final

    def to_bar_event(self) -> BarEvent:
        """Convert the normalized bar into the domain BarEvent contract."""
        return BarEvent(
            exchange=self.exchange,
            symbol=self.symbol,
            timeframe=self.timeframe,
            bar_start_time=self.bar_start_time,
            bar_end_time=self.bar_end_time,
            event_time=self.bar_end_time,
            ingest_time=self.ingest_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            quote_volume=self.quote_volume,
            trade_count=self.trade_count,
            closed=self.closed,
            final=self.final,
            source_kind=self.source_kind,
            market_state=self.market_state,
            source_payload=self.source_payload,
        )


@dataclass(slots=True, frozen=True)
class BarEmissionDecision:
    """Describe whether a normalized bar should enter the tradable chain."""

    status: Literal["emit", "duplicate", "non_actionable"]
    event: BarEvent
    reason: str


class FinalBarGate:
    """Deduplicate final bars while ignoring unfinished realtime updates."""

    def __init__(self, *, recent_final_capacity: int = 4096) -> None:
        if recent_final_capacity < 1:
            raise ValueError("recent_final_capacity must be at least 1")

        self._recent_final_capacity = recent_final_capacity
        self._recent_final_keys: deque[str] = deque()
        self._recent_final_lookup: set[str] = set()
        self._last_final_by_stream: dict[str, BarEvent] = {}

    def process(self, bar: NormalizedBar) -> BarEmissionDecision:
        """Return whether the bar should be emitted downstream."""
        event = bar.to_bar_event()
        if not event.actionable:
            return BarEmissionDecision(
                status="non_actionable",
                event=event,
                reason="bar_is_not_closed_and_final",
            )

        if event.bar_key in self._recent_final_lookup:
            return BarEmissionDecision(
                status="duplicate",
                event=event,
                reason="bar_key_already_emitted",
            )

        self._remember(event)
        return BarEmissionDecision(status="emit", event=event, reason="new_final_bar")

    def last_final_bar(self, exchange: str, symbol: str, timeframe: str) -> BarEvent | None:
        """Return the latest emitted final bar for a stream, if known."""
        return self._last_final_by_stream.get(build_bar_stream_key(exchange, symbol, timeframe))

    def next_expected_bar_start(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
    ) -> datetime | None:
        """Return the next missing bar start for backfill, if a final bar exists."""
        last_bar = self.last_final_bar(exchange, symbol, timeframe)
        if last_bar is None:
            return None
        return last_bar.bar_start_time + timeframe_to_timedelta(timeframe)

    def _remember(self, event: BarEvent) -> None:
        self._recent_final_lookup.add(event.bar_key)
        self._recent_final_keys.append(event.bar_key)
        stream_key = build_bar_stream_key(event.exchange, event.symbol, event.timeframe)
        self._last_final_by_stream[stream_key] = event

        while len(self._recent_final_keys) > self._recent_final_capacity:
            expired_key = self._recent_final_keys.popleft()
            self._recent_final_lookup.discard(expired_key)
