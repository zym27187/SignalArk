"""Portfolio-domain state objects."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from src.shared.types import (
    DomainEntity,
    NonEmptyStr,
    NonNegativeDecimal,
    PositiveDecimal,
    UtcDateTime,
    utc_now,
)


class PositionSide(StrEnum):
    """Supported V1 position directions."""

    LONG = "LONG"


class PositionStatus(StrEnum):
    """Lifecycle states for spot positions."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Position(DomainEntity):
    """Current per-symbol position state derived from fills."""

    account_id: NonEmptyStr
    exchange: NonEmptyStr
    symbol: NonEmptyStr
    side: PositionSide = PositionSide.LONG
    qty: NonNegativeDecimal = Decimal("0")
    avg_entry_price: PositiveDecimal | None = None
    mark_price: PositiveDecimal | None = None
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    status: PositionStatus = PositionStatus.CLOSED
    updated_at: UtcDateTime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_position_contract(self) -> Position:
        """Validate spot-only position invariants."""
        if self.qty == 0:
            if self.status != PositionStatus.CLOSED:
                raise ValueError("Zero-qty positions must be CLOSED")
            if self.avg_entry_price is not None:
                raise ValueError("Zero-qty positions cannot keep avg_entry_price")
            if self.unrealized_pnl != 0:
                raise ValueError("Closed positions must have zero unrealized_pnl")
            return self

        if self.status != PositionStatus.OPEN:
            raise ValueError("Non-zero positions must be OPEN")

        if self.avg_entry_price is None:
            raise ValueError("Open positions require avg_entry_price")

        return self


class BalanceSnapshot(DomainEntity):
    """A point-in-time balance view for one asset inside one account."""

    account_id: NonEmptyStr
    exchange: NonEmptyStr
    asset: NonEmptyStr
    total: NonNegativeDecimal
    available: NonNegativeDecimal
    locked: NonNegativeDecimal
    snapshot_time: UtcDateTime
    created_at: UtcDateTime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_balance_contract(self) -> BalanceSnapshot:
        """Validate the snapshot arithmetic contract."""
        if self.available + self.locked != self.total:
            raise ValueError("BalanceSnapshot requires total == available + locked")

        if self.created_at < self.snapshot_time:
            raise ValueError("created_at cannot be earlier than snapshot_time")

        return self
