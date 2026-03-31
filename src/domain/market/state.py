"""Market-state contracts shared across collector, risk, and execution."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import model_validator

from src.shared.types import DomainModel, PositiveDecimal

SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")


class TradingPhase(StrEnum):
    """Minimal A-share trading-phase contract needed by later checks."""

    PRE_OPEN = "PRE_OPEN"
    CONTINUOUS_AUCTION = "CONTINUOUS_AUCTION"
    MIDDAY_BREAK = "MIDDAY_BREAK"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class SuspensionStatus(StrEnum):
    """Minimal security suspension contract used in A-share V1."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


class MarketStateSnapshot(DomainModel):
    """Minimal market-state snapshot required by A-share V1 execution checks."""

    trade_date: date
    previous_close: PositiveDecimal
    upper_limit_price: PositiveDecimal
    lower_limit_price: PositiveDecimal
    trading_phase: TradingPhase
    suspension_status: SuspensionStatus

    @model_validator(mode="after")
    def validate_price_limits(self) -> MarketStateSnapshot:
        """Keep price-limit inputs causally consistent."""
        if self.upper_limit_price <= self.lower_limit_price:
            raise ValueError("upper_limit_price must be greater than lower_limit_price")
        if not self.lower_limit_price <= self.previous_close <= self.upper_limit_price:
            raise ValueError("previous_close must stay within the derived price limits")
        return self


def derive_a_share_trading_phase(at: datetime) -> TradingPhase:
    """Derive the minimal A-share trading phase from a Shanghai-local timestamp."""
    local_time = at.astimezone(SHANGHAI_TIMEZONE).time()

    if time(9, 15) <= local_time < time(9, 30):
        return TradingPhase.PRE_OPEN
    if time(9, 30) <= local_time < time(11, 30):
        return TradingPhase.CONTINUOUS_AUCTION
    if time(11, 30) <= local_time < time(13, 0):
        return TradingPhase.MIDDAY_BREAK
    if time(13, 0) <= local_time < time(15, 0):
        return TradingPhase.CONTINUOUS_AUCTION
    return TradingPhase.CLOSED


def compute_price_limits(
    previous_close: Decimal,
    price_limit_pct: Decimal,
    *,
    price_tick: Decimal,
) -> tuple[Decimal, Decimal]:
    """Derive rounded A-share upper/lower price limits from previous close."""
    upper_limit = (previous_close * (Decimal("1") + price_limit_pct)).quantize(
        price_tick,
        rounding=ROUND_HALF_UP,
    )
    lower_limit = (previous_close * (Decimal("1") - price_limit_pct)).quantize(
        price_tick,
        rounding=ROUND_HALF_UP,
    )
    return upper_limit, lower_limit


def build_market_state_snapshot(
    *,
    event_time: datetime,
    previous_close: Decimal,
    price_limit_pct: Decimal,
    price_tick: Decimal,
    suspension_status: SuspensionStatus,
) -> MarketStateSnapshot:
    """Build the normalized A-share market-state snapshot for one bar event."""
    upper_limit_price, lower_limit_price = compute_price_limits(
        previous_close,
        price_limit_pct,
        price_tick=price_tick,
    )
    local_event_time = event_time.astimezone(SHANGHAI_TIMEZONE)
    return MarketStateSnapshot(
        trade_date=local_event_time.date(),
        previous_close=previous_close,
        upper_limit_price=upper_limit_price,
        lower_limit_price=lower_limit_price,
        trading_phase=derive_a_share_trading_phase(local_event_time),
        suspension_status=suspension_status,
    )
