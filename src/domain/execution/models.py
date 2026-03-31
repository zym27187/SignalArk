"""Execution-domain objects and order lifecycle rules."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from src.shared.types import (
    DomainEntity,
    DomainId,
    NonEmptyStr,
    NonNegativeDecimal,
    PositiveDecimal,
    UtcDateTime,
    utc_now,
)


class OrderSide(StrEnum):
    """Execution-side order directions."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    """Supported V1 order types."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"


class TimeInForce(StrEnum):
    """Supported V1 time-in-force values."""

    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class OrderStatus(StrEnum):
    """OMS-visible order lifecycle states."""

    NEW = "NEW"
    ACK = "ACK"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class LiquidityType(StrEnum):
    """Execution liquidity classification for fills."""

    MAKER = "MAKER"
    TAKER = "TAKER"
    UNKNOWN = "UNKNOWN"


ORDER_STATUS_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.NEW: frozenset({OrderStatus.ACK, OrderStatus.REJECTED, OrderStatus.CANCELED}),
    OrderStatus.ACK: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELED,
            OrderStatus.REJECTED,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELED}
    ),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.CANCELED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
}


class OrderStateTransitionError(ValueError):
    """Raised when an invalid order status transition is attempted."""


def can_transition_order_status(current: OrderStatus, new: OrderStatus) -> bool:
    """Return whether the order status transition is permitted."""
    if current == new:
        return True
    return new in ORDER_STATUS_TRANSITIONS[current]


def validate_order_status_transition(current: OrderStatus, new: OrderStatus) -> None:
    """Raise if an order status transition violates the state machine."""
    if can_transition_order_status(current, new):
        return
    raise OrderStateTransitionError(f"Invalid order status transition: {current} -> {new}")


def _validate_order_pricing(
    *,
    order_type: OrderType,
    price: Decimal | None,
    decision_price: Decimal | None = None,
    require_decision_price: bool = False,
) -> Decimal | None:
    """Apply the V1 price contract for market and limit orders."""
    if order_type == OrderType.MARKET:
        if price is not None:
            raise ValueError("MARKET orders must not carry a resting order price")
        if require_decision_price and decision_price is None:
            raise ValueError("MARKET orders require decision_price for sizing and risk")
        return decision_price

    if price is None:
        raise ValueError("LIMIT orders must provide price")

    return decision_price if decision_price is not None else price


class OrderIntent(DomainEntity):
    """A post-risk, pre-execution instruction to submit a specific order."""

    signal_id: DomainId
    strategy_id: NonEmptyStr
    trader_run_id: DomainId
    account_id: NonEmptyStr
    exchange: NonEmptyStr
    symbol: NonEmptyStr

    side: OrderSide
    order_type: OrderType
    time_in_force: TimeInForce = TimeInForce.GTC
    qty: PositiveDecimal
    price: PositiveDecimal | None = None
    decision_price: PositiveDecimal | None = None
    reduce_only: bool = False
    idempotency_key: NonEmptyStr
    created_at: UtcDateTime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def normalize_order_intent_pricing(cls, data: object) -> object:
        """Fill in default decision_price for limit intents before validation."""
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        order_type = payload.get("order_type")
        if order_type is None:
            return payload

        payload["decision_price"] = _validate_order_pricing(
            order_type=OrderType(order_type),
            price=payload.get("price"),
            decision_price=payload.get("decision_price"),
            require_decision_price=True,
        )
        return payload

    @model_validator(mode="after")
    def validate_order_intent_contract(self) -> OrderIntent:
        """Validate the distinction between target position and executable order qty."""
        if self.reduce_only and self.side != OrderSide.SELL:
            raise ValueError("reduce_only intents can only use SELL side in V1 spot mode")

        return self

    @property
    def notional(self) -> Decimal:
        """Return the reference notional used by sizing and risk checks."""
        assert self.decision_price is not None
        return self.qty * self.decision_price


class Order(DomainEntity):
    """An execution-stage order that lives inside the OMS state machine."""

    order_intent_id: DomainId
    trader_run_id: DomainId
    exchange_order_id: str | None = None
    account_id: NonEmptyStr
    exchange: NonEmptyStr
    symbol: NonEmptyStr

    side: OrderSide
    order_type: OrderType
    time_in_force: TimeInForce = TimeInForce.GTC
    qty: PositiveDecimal
    price: PositiveDecimal | None = None
    filled_qty: NonNegativeDecimal = Decimal("0")
    avg_fill_price: PositiveDecimal | None = None
    status: OrderStatus = OrderStatus.NEW
    submitted_at: UtcDateTime = Field(default_factory=utc_now)
    updated_at: UtcDateTime = Field(default_factory=utc_now)
    last_error_code: str | None = None
    last_error_message: str | None = None

    @model_validator(mode="after")
    def validate_order_contract(self) -> Order:
        """Validate pricing, fill aggregates, and status invariants."""
        _validate_order_pricing(order_type=self.order_type, price=self.price)

        if self.filled_qty > self.qty:
            raise ValueError("filled_qty cannot exceed qty")

        if self.submitted_at > self.updated_at:
            raise ValueError("updated_at cannot be earlier than submitted_at")

        if self.avg_fill_price is not None and self.filled_qty == 0:
            raise ValueError("avg_fill_price requires filled_qty greater than zero")

        if self.status in {OrderStatus.NEW, OrderStatus.ACK, OrderStatus.REJECTED}:
            if self.filled_qty != 0:
                raise ValueError(f"{self.status} orders cannot have any filled_qty")
            if self.status == OrderStatus.REJECTED and self.avg_fill_price is not None:
                raise ValueError("REJECTED orders cannot have avg_fill_price")

        if self.status == OrderStatus.PARTIALLY_FILLED:
            if not (0 < self.filled_qty < self.qty):
                raise ValueError("PARTIALLY_FILLED orders must have 0 < filled_qty < qty")
            if self.avg_fill_price is None:
                raise ValueError("PARTIALLY_FILLED orders require avg_fill_price")

        if self.status == OrderStatus.FILLED:
            if self.filled_qty != self.qty:
                raise ValueError("FILLED orders must have filled_qty equal to qty")
            if self.avg_fill_price is None:
                raise ValueError("FILLED orders require avg_fill_price")

        if (
            self.status == OrderStatus.CANCELED
            and self.filled_qty > 0
            and self.avg_fill_price is None
        ):
            raise ValueError("Partially filled canceled orders require avg_fill_price")

        return self

    @property
    def remaining_qty(self) -> Decimal:
        """Return the unfilled quantity still resting or pending."""
        return self.qty - self.filled_qty

    def transition_to(self, new_status: OrderStatus, **updates: object) -> Order:
        """Return a validated copy with the requested order status transition."""
        validate_order_status_transition(self.status, new_status)
        payload = self.model_dump()
        payload.update(updates)
        payload["status"] = new_status
        payload.setdefault("updated_at", utc_now())
        return type(self)(**payload)


class Fill(DomainEntity):
    """A normalized execution fill that drives position and balance updates."""

    order_id: DomainId
    trader_run_id: DomainId
    exchange_fill_id: str | None = None
    account_id: NonEmptyStr
    exchange: NonEmptyStr
    symbol: NonEmptyStr

    side: OrderSide
    qty: PositiveDecimal
    price: PositiveDecimal
    fee: NonNegativeDecimal = Decimal("0")
    fee_asset: str | None = None
    liquidity_type: LiquidityType = LiquidityType.UNKNOWN
    fill_time: UtcDateTime
    created_at: UtcDateTime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_fill_contract(self) -> Fill:
        """Validate fee semantics and fill timestamps."""
        if self.fee > 0 and not self.fee_asset:
            raise ValueError("fee_asset is required when fee is greater than zero")

        if self.created_at < self.fill_time:
            raise ValueError("created_at cannot be earlier than fill_time")

        return self

    @property
    def notional(self) -> Decimal:
        """Return the gross notional traded by this fill."""
        return self.qty * self.price
