"""Standardized market bar event models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field, computed_field, model_validator

from src.shared.types import (
    DomainEntity,
    NonNegativeDecimal,
    PositiveDecimal,
    TimeframeStr,
    UtcDateTime,
)


class BarEvent(DomainEntity):
    """A normalized OHLCV bar used as the primary V1 market event."""

    exchange: str
    symbol: str
    timeframe: TimeframeStr

    bar_start_time: UtcDateTime
    bar_end_time: UtcDateTime
    event_time: UtcDateTime
    ingest_time: UtcDateTime

    open: PositiveDecimal
    high: PositiveDecimal
    low: PositiveDecimal
    close: PositiveDecimal
    volume: NonNegativeDecimal
    quote_volume: NonNegativeDecimal | None = None
    trade_count: int | None = Field(default=None, ge=0)

    closed: bool = False
    final: bool = False

    @model_validator(mode="after")
    def validate_bar_window(self) -> BarEvent:
        """Validate bar window, price consistency, and finality semantics."""
        if self.bar_end_time <= self.bar_start_time:
            raise ValueError("bar_end_time must be later than bar_start_time")

        if self.event_time != self.bar_end_time:
            raise ValueError("event_time must equal bar_end_time for BarEvent")

        if self.ingest_time < self.bar_start_time:
            raise ValueError("ingest_time cannot be earlier than bar_start_time")

        if self.high < max(self.open, self.close):
            raise ValueError("high must be greater than or equal to open and close")

        if self.low > min(self.open, self.close):
            raise ValueError("low must be less than or equal to open and close")

        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")

        if self.final and not self.closed:
            raise ValueError("final bars must also be closed")

        return self

    @computed_field(return_type=str)
    @property
    def bar_key(self) -> str:
        """Return the stable deduplication key for this bar window."""
        return ":".join(
            [self.exchange, self.symbol, self.timeframe, self.bar_start_time.isoformat()]
        )

    @property
    def time_window(self) -> tuple[datetime, datetime]:
        """Return the half-open time window represented by this bar."""
        return (self.bar_start_time, self.bar_end_time)

    @property
    def actionable(self) -> bool:
        """V1 strategies may only trade on closed and final bars."""
        return self.closed and self.final

    @property
    def decision_price(self) -> Decimal:
        """The default reference price used by later sizing and risk decisions."""
        return self.close
