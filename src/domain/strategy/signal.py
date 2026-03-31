"""Strategy-domain contracts and signal models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from src.shared.types import (
    DomainEntity,
    DomainId,
    NonEmptyStr,
    NonNegativeDecimal,
    ShanghaiDateTime,
    TimeframeStr,
    UnitIntervalDecimal,
    shanghai_now,
)


class SignalType(StrEnum):
    """High-level strategy intent without turning it into an order."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REDUCE = "REDUCE"
    REBALANCE = "REBALANCE"


class SignalStatus(StrEnum):
    """Persistence-visible lifecycle states for strategy signals."""

    NEW = "NEW"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class Signal(DomainEntity):
    """A strategy output that proposes a target post-trade position."""

    strategy_id: NonEmptyStr
    trader_run_id: DomainId
    account_id: NonEmptyStr
    exchange: NonEmptyStr
    symbol: NonEmptyStr
    timeframe: TimeframeStr

    signal_type: SignalType
    target_position: NonNegativeDecimal
    confidence: UnitIntervalDecimal | None = None
    reason_summary: str | None = None
    status: SignalStatus = SignalStatus.NEW

    event_time: ShanghaiDateTime
    created_at: ShanghaiDateTime = Field(default_factory=shanghai_now)

    @model_validator(mode="after")
    def validate_signal_contract(self) -> Signal:
        """Validate the sizing contract and signal timing semantics."""
        if self.signal_type == SignalType.ENTRY and self.target_position == 0:
            raise ValueError("ENTRY signals must target a positive post-trade position")

        if self.signal_type == SignalType.EXIT and self.target_position != 0:
            raise ValueError("EXIT signals must target a flat post-trade position")

        if self.created_at < self.event_time:
            raise ValueError("created_at cannot be earlier than event_time")

        return self

    @property
    def is_flatten_signal(self) -> bool:
        """Return whether the strategy wants the resulting position to be flat."""
        return self.target_position == 0
