"""OMS sizing and order-construction helpers for Phase 5A."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from src.domain.execution.models import (
    ExecutionReport,
    Order,
    OrderIntent,
    OrderSide,
    OrderStatus,
    OrderType,
    OrderUpdate,
    TimeInForce,
)
from src.domain.market import MarketStateSnapshot
from src.domain.portfolio import Position
from src.domain.strategy import Signal
from src.shared.types import shanghai_now


class SymbolRuleLike(Protocol):
    """Minimal A-share symbol-rule contract needed by Phase 5A sizing."""

    lot_size: Decimal
    qty_step: Decimal
    min_qty: Decimal
    allow_odd_lot_sell: bool


class SignalOrderIntentError(ValueError):
    """Raised when Signal -> OrderIntent conversion cannot be constructed safely."""


@dataclass(frozen=True, slots=True)
class SignalOrderIntentPlan:
    """A deterministic sizing result before the intent is persisted."""

    signal: Signal
    side: OrderSide | None
    qty: Decimal
    target_position: Decimal
    current_position_qty: Decimal
    current_sellable_qty: Decimal
    raw_delta_qty: Decimal
    decision_price: Decimal
    market_context: MarketStateSnapshot
    reduce_only: bool
    odd_lot_sell: bool = False
    skip_reason: str | None = None
    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    price: Decimal | None = None

    @property
    def actionable(self) -> bool:
        """Return whether the plan should become a persisted OrderIntent."""
        return self.side is not None and self.qty > 0 and self.skip_reason is None

    def to_order_intent(
        self,
        *,
        idempotency_key: str | None = None,
        created_at: datetime | None = None,
    ) -> OrderIntent:
        """Materialize the persisted post-risk OrderIntent."""
        if not self.actionable or self.side is None:
            raise SignalOrderIntentError(
                f"Cannot build OrderIntent from a non-actionable plan: {self.skip_reason}"
            )

        return OrderIntent(
            signal_id=self.signal.id,
            strategy_id=self.signal.strategy_id,
            trader_run_id=self.signal.trader_run_id,
            account_id=self.signal.account_id,
            exchange=self.signal.exchange,
            symbol=self.signal.symbol,
            side=self.side,
            order_type=self.order_type,
            time_in_force=self.time_in_force,
            qty=self.qty,
            price=self.price,
            decision_price=self.decision_price,
            reduce_only=self.reduce_only,
            market_context_json=self.market_context,
            idempotency_key=idempotency_key or build_order_intent_idempotency_key(self.signal),
            created_at=created_at or shanghai_now(),
        )


def build_order_intent_idempotency_key(signal: Signal) -> str:
    """Return the stable idempotency key for one signal-driven order intent."""
    return f"signalark:signal:{signal.id}:order_intent"


def build_order_id_for_intent(order_intent_id: UUID) -> UUID:
    """Derive a stable order ID so retries do not create duplicate OMS orders."""
    return uuid5(NAMESPACE_URL, f"signalark:order:{order_intent_id}")


def create_order_from_intent(
    order_intent: OrderIntent,
    *,
    order_id: UUID | None = None,
    exchange_order_id: str | None = None,
    submitted_at: datetime | None = None,
    status: OrderStatus = OrderStatus.NEW,
) -> Order:
    """Promote a persisted intent into the OMS order state machine."""
    timestamp = submitted_at or shanghai_now()
    return Order(
        id=order_id or build_order_id_for_intent(order_intent.id),
        order_intent_id=order_intent.id,
        trader_run_id=order_intent.trader_run_id,
        exchange_order_id=exchange_order_id,
        account_id=order_intent.account_id,
        exchange=order_intent.exchange,
        symbol=order_intent.symbol,
        side=order_intent.side,
        order_type=order_intent.order_type,
        time_in_force=order_intent.time_in_force,
        qty=order_intent.qty,
        price=order_intent.price,
        status=status,
        submitted_at=timestamp,
        updated_at=timestamp,
    )


def apply_order_update(order: Order, update: OrderUpdate) -> Order:
    """Apply one normalized execution update onto the persisted OMS order."""
    if order.id != update.order_id:
        raise ValueError("order.id must match update.order_id")
    if order.order_intent_id != update.order_intent_id:
        raise ValueError("order.order_intent_id must match update.order_intent_id")
    if order.trader_run_id != update.trader_run_id:
        raise ValueError("order.trader_run_id must match update.trader_run_id")
    if order.account_id != update.account_id:
        raise ValueError("order.account_id must match update.account_id")
    if order.exchange != update.exchange:
        raise ValueError("order.exchange must match update.exchange")
    if order.symbol != update.symbol:
        raise ValueError("order.symbol must match update.symbol")
    if (
        order.exchange_order_id is not None
        and update.exchange_order_id is not None
        and order.exchange_order_id != update.exchange_order_id
    ):
        raise ValueError("update.exchange_order_id cannot replace an existing exchange_order_id")

    return order.transition_to(
        update.status,
        exchange_order_id=update.exchange_order_id or order.exchange_order_id,
        filled_qty=update.filled_qty,
        avg_fill_price=update.avg_fill_price,
        updated_at=update.event_time,
        last_error_code=update.error_code,
        last_error_message=update.error_message,
    )


def execution_report_is_empty(report: ExecutionReport) -> bool:
    """Return whether an execution report contains any order or fill events."""
    return not report.order_updates and not report.fill_events


def build_signal_order_intent_plan(
    *,
    signal: Signal,
    symbol_rule: SymbolRuleLike,
    current_position: Position | None,
    decision_price: Decimal,
    market_context: MarketStateSnapshot,
    order_type: OrderType = OrderType.MARKET,
    price: Decimal | None = None,
) -> SignalOrderIntentPlan:
    """Convert target position into a deterministic executable order delta."""
    if decision_price <= 0:
        raise SignalOrderIntentError("decision_price must be positive")

    _validate_position_matches_signal(signal=signal, current_position=current_position)

    current_position_qty = current_position.qty if current_position is not None else Decimal("0")
    current_sellable_qty = (
        current_position.sellable_qty if current_position is not None else Decimal("0")
    )
    raw_delta_qty = signal.target_position - current_position_qty

    if raw_delta_qty == 0:
        return SignalOrderIntentPlan(
            signal=signal,
            side=None,
            qty=Decimal("0"),
            target_position=signal.target_position,
            current_position_qty=current_position_qty,
            current_sellable_qty=current_sellable_qty,
            raw_delta_qty=raw_delta_qty,
            decision_price=decision_price,
            market_context=market_context,
            reduce_only=False,
            skip_reason="target_position_already_satisfied",
            order_type=order_type,
            price=price,
        )

    if raw_delta_qty > 0:
        normalized_qty = _floor_to_step(raw_delta_qty, symbol_rule.qty_step)
        if normalized_qty < symbol_rule.min_qty:
            return SignalOrderIntentPlan(
                signal=signal,
                side=None,
                qty=Decimal("0"),
                target_position=signal.target_position,
                current_position_qty=current_position_qty,
                current_sellable_qty=current_sellable_qty,
                raw_delta_qty=raw_delta_qty,
                decision_price=decision_price,
                market_context=market_context,
                reduce_only=False,
                skip_reason="normalized_buy_qty_below_min_qty",
                order_type=order_type,
                price=price,
            )

        return SignalOrderIntentPlan(
            signal=signal,
            side=OrderSide.BUY,
            qty=normalized_qty,
            target_position=signal.target_position,
            current_position_qty=current_position_qty,
            current_sellable_qty=current_sellable_qty,
            raw_delta_qty=raw_delta_qty,
            decision_price=decision_price,
            market_context=market_context,
            reduce_only=False,
            order_type=order_type,
            price=price,
        )

    desired_sell_qty = min(abs(raw_delta_qty), current_sellable_qty)
    if desired_sell_qty <= 0:
        return SignalOrderIntentPlan(
            signal=signal,
            side=None,
            qty=Decimal("0"),
            target_position=signal.target_position,
            current_position_qty=current_position_qty,
            current_sellable_qty=current_sellable_qty,
            raw_delta_qty=raw_delta_qty,
            decision_price=decision_price,
            market_context=market_context,
            reduce_only=True,
            skip_reason="sellable_qty_exhausted",
            order_type=order_type,
            price=price,
        )

    odd_lot_sell = (
        Decimal("0") < current_sellable_qty < symbol_rule.lot_size
        and symbol_rule.allow_odd_lot_sell
        and desired_sell_qty >= current_sellable_qty
    )

    if odd_lot_sell:
        normalized_qty = current_sellable_qty
    else:
        normalized_qty = _floor_to_step(desired_sell_qty, symbol_rule.qty_step)
        if normalized_qty < symbol_rule.min_qty:
            return SignalOrderIntentPlan(
                signal=signal,
                side=None,
                qty=Decimal("0"),
                target_position=signal.target_position,
                current_position_qty=current_position_qty,
                current_sellable_qty=current_sellable_qty,
                raw_delta_qty=raw_delta_qty,
                decision_price=decision_price,
                market_context=market_context,
                reduce_only=True,
                skip_reason="normalized_sell_qty_below_min_qty",
                order_type=order_type,
                price=price,
            )

    return SignalOrderIntentPlan(
        signal=signal,
        side=OrderSide.SELL,
        qty=normalized_qty,
        target_position=signal.target_position,
        current_position_qty=current_position_qty,
        current_sellable_qty=current_sellable_qty,
        raw_delta_qty=raw_delta_qty,
        decision_price=decision_price,
        market_context=market_context,
        reduce_only=True,
        odd_lot_sell=odd_lot_sell,
        order_type=order_type,
        price=price,
    )


def _validate_position_matches_signal(*, signal: Signal, current_position: Position | None) -> None:
    if current_position is None:
        return

    if current_position.account_id != signal.account_id:
        raise SignalOrderIntentError("current_position.account_id must match signal.account_id")
    if current_position.exchange != signal.exchange:
        raise SignalOrderIntentError("current_position.exchange must match signal.exchange")
    if current_position.symbol != signal.symbol:
        raise SignalOrderIntentError("current_position.symbol must match signal.symbol")


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if value <= 0:
        return Decimal("0")

    increments = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return increments * step
