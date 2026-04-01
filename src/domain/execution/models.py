"""Execution-domain objects and order lifecycle rules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from src.domain.market import MarketStateSnapshot
from src.shared.types import (
    DomainEntity,
    DomainId,
    DomainModel,
    NonEmptyStr,
    NonNegativeDecimal,
    PositiveDecimal,
    ShanghaiDateTime,
    shanghai_now,
)


class OrderSide(StrEnum):
    """Execution-side order directions."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    """Supported V1 execution styles for A-share paper trading."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"


class TimeInForce(StrEnum):
    """Supported V1 order-validity values."""

    DAY = "DAY"


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


class OrderIntentStatus(StrEnum):
    """Lifecycle states for persisted pre-execution order intents."""

    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class RiskDecision(StrEnum):
    """Pre-trade risk verdict captured on persisted order intents."""

    ALLOW = "ALLOW"
    REJECT = "REJECT"


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
    """Apply the V1 pricing contract for limit and paper-market orders."""
    if order_type == OrderType.MARKET:
        if price is not None:
            raise ValueError("MARKET orders must not carry a resting order price")
        if require_decision_price and decision_price is None:
            raise ValueError("MARKET orders require decision_price for sizing and risk")
        return decision_price

    if price is None:
        raise ValueError("LIMIT orders must provide price")

    return decision_price if decision_price is not None else price


def _jsonable_market_context(value: Any) -> Any:
    """Normalize market-context values into JSON-safe primitives."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable_market_context(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_jsonable_market_context(item) for item in value]
    return str(value)


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
    time_in_force: TimeInForce = TimeInForce.DAY
    qty: PositiveDecimal
    price: PositiveDecimal | None = None
    decision_price: PositiveDecimal | None = None
    reduce_only: bool = False
    market_context_json: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: NonEmptyStr
    status: OrderIntentStatus = OrderIntentStatus.NEW
    risk_decision: RiskDecision = RiskDecision.ALLOW
    risk_reason: str | None = None
    created_at: ShanghaiDateTime = Field(default_factory=shanghai_now)

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

    @field_validator("market_context_json", mode="before")
    @classmethod
    def normalize_market_context(cls, value: object) -> dict[str, Any]:
        """Accept either a typed market snapshot or a JSON-like mapping."""
        if value is None:
            return {}
        if isinstance(value, MarketStateSnapshot):
            return value.model_dump(mode="json")
        if not isinstance(value, Mapping):
            raise TypeError("market_context_json must be a mapping or MarketStateSnapshot")
        return _jsonable_market_context(value)

    @model_validator(mode="after")
    def validate_order_intent_contract(self) -> OrderIntent:
        """Validate the distinction between target position and executable order qty."""
        if self.reduce_only and self.side != OrderSide.SELL:
            raise ValueError("reduce_only intents can only use SELL side in V1 long-only mode")

        if self.order_type == OrderType.LIMIT and not self.market_context_json:
            raise ValueError("LIMIT orders require market_context_json in A-share V1")

        if self.market_context_json:
            MarketStateSnapshot(**self.market_context_json)

        return self

    @property
    def notional(self) -> Decimal:
        """Return the reference notional used by sizing and risk checks."""
        assert self.decision_price is not None
        return self.qty * self.decision_price

    @property
    def market_state(self) -> MarketStateSnapshot | None:
        """Return the typed market-state snapshot when one was persisted."""
        if not self.market_context_json:
            return None
        return MarketStateSnapshot(**self.market_context_json)


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
    time_in_force: TimeInForce = TimeInForce.DAY
    qty: PositiveDecimal
    price: PositiveDecimal | None = None
    filled_qty: NonNegativeDecimal = Decimal("0")
    avg_fill_price: PositiveDecimal | None = None
    status: OrderStatus = OrderStatus.NEW
    submitted_at: ShanghaiDateTime = Field(default_factory=shanghai_now)
    updated_at: ShanghaiDateTime = Field(default_factory=shanghai_now)
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
        payload.setdefault("updated_at", shanghai_now())
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
    fill_time: ShanghaiDateTime
    created_at: ShanghaiDateTime = Field(default_factory=shanghai_now)

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


class AshareExecutionCostBreakdown(DomainModel):
    """A-share paper-trading cost fields reserved for the later ledger stage."""

    currency: NonEmptyStr = "CNY"
    gross_notional: NonNegativeDecimal
    commission: NonNegativeDecimal = Decimal("0")
    transfer_fee: NonNegativeDecimal = Decimal("0")
    stamp_duty: NonNegativeDecimal = Decimal("0")
    total_fee: NonNegativeDecimal
    net_cash_flow: Decimal

    @model_validator(mode="after")
    def validate_cost_breakdown(self) -> AshareExecutionCostBreakdown:
        """Keep component fees and the aggregate total in sync."""
        expected_total = self.commission + self.transfer_fee + self.stamp_duty
        if self.total_fee != expected_total:
            raise ValueError("total_fee must equal commission + transfer_fee + stamp_duty")
        return self


class OrderUpdate(DomainEntity):
    """A normalized execution-side order update consumed by the OMS."""

    order_id: DomainId
    order_intent_id: DomainId
    trader_run_id: DomainId
    account_id: NonEmptyStr
    exchange: NonEmptyStr
    symbol: NonEmptyStr

    status: OrderStatus
    exchange_order_id: str | None = None
    filled_qty: NonNegativeDecimal = Decimal("0")
    avg_fill_price: PositiveDecimal | None = None
    error_code: str | None = None
    error_message: str | None = None
    event_time: ShanghaiDateTime
    created_at: ShanghaiDateTime = Field(default_factory=shanghai_now)

    @model_validator(mode="after")
    def validate_order_update_contract(self) -> OrderUpdate:
        """Apply the same fill-aggregate invariants the OMS order model enforces."""
        if self.avg_fill_price is not None and self.filled_qty == 0:
            raise ValueError("avg_fill_price requires filled_qty greater than zero")

        if self.status in {OrderStatus.NEW, OrderStatus.ACK, OrderStatus.REJECTED}:
            if self.filled_qty != 0:
                raise ValueError(f"{self.status} updates cannot carry filled_qty")
            if self.status == OrderStatus.REJECTED and self.avg_fill_price is not None:
                raise ValueError("REJECTED updates cannot carry avg_fill_price")

        if self.status == OrderStatus.PARTIALLY_FILLED:
            if self.filled_qty <= 0:
                raise ValueError("PARTIALLY_FILLED updates require filled_qty greater than zero")
            if self.avg_fill_price is None:
                raise ValueError("PARTIALLY_FILLED updates require avg_fill_price")

        if self.status == OrderStatus.FILLED:
            if self.filled_qty <= 0:
                raise ValueError("FILLED updates require filled_qty greater than zero")
            if self.avg_fill_price is None:
                raise ValueError("FILLED updates require avg_fill_price")

        if (
            self.status == OrderStatus.CANCELED
            and self.filled_qty > 0
            and self.avg_fill_price is None
        ):
            raise ValueError("Partially filled canceled updates require avg_fill_price")

        if self.created_at < self.event_time:
            raise ValueError("created_at cannot be earlier than event_time")

        return self


class FillEvent(DomainEntity):
    """A normalized fill event plus the A-share cost breakdown reserved for Phase 5C."""

    order_id: DomainId
    order_intent_id: DomainId
    trader_run_id: DomainId
    account_id: NonEmptyStr
    exchange: NonEmptyStr
    symbol: NonEmptyStr
    fill: Fill
    cost_breakdown: AshareExecutionCostBreakdown
    event_time: ShanghaiDateTime
    created_at: ShanghaiDateTime = Field(default_factory=shanghai_now)

    @model_validator(mode="after")
    def validate_fill_event_contract(self) -> FillEvent:
        """Keep the envelope fields aligned with the embedded fill payload."""
        if self.order_id != self.fill.order_id:
            raise ValueError("order_id must match fill.order_id")
        if self.trader_run_id != self.fill.trader_run_id:
            raise ValueError("trader_run_id must match fill.trader_run_id")
        if self.account_id != self.fill.account_id:
            raise ValueError("account_id must match fill.account_id")
        if self.exchange != self.fill.exchange:
            raise ValueError("exchange must match fill.exchange")
        if self.symbol != self.fill.symbol:
            raise ValueError("symbol must match fill.symbol")
        if self.cost_breakdown.gross_notional != self.fill.notional:
            raise ValueError("cost_breakdown.gross_notional must match fill.notional")
        if self.cost_breakdown.total_fee != self.fill.fee:
            raise ValueError("cost_breakdown.total_fee must match fill.fee")
        if self.event_time < self.fill.fill_time:
            raise ValueError("event_time cannot be earlier than fill.fill_time")
        if self.created_at < self.event_time:
            raise ValueError("created_at cannot be earlier than event_time")
        return self


class ExecutionReport(DomainModel):
    """The standard execution result returned by one adapter interaction."""

    source: NonEmptyStr = "execution_gateway"
    order_updates: tuple[OrderUpdate, ...] = ()
    fill_events: tuple[FillEvent, ...] = ()
