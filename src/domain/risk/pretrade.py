"""Unified pre-trade risk gate for Phase 6A."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import Field

from src.config.settings import AshareSymbolRule
from src.domain.execution import (
    OrderIntent,
    OrderSide,
    OrderType,
    RiskDecision,
    SignalOrderIntentPlan,
)
from src.domain.market import (
    MarketStateSnapshot,
    SuspensionStatus,
    TradingPhase,
    timeframe_to_timedelta,
)
from src.domain.portfolio import Position
from src.domain.strategy import Signal
from src.shared.types import DomainModel


class RiskControlState(StrEnum):
    """Control states that can tighten the order-entry boundary."""

    NORMAL = "normal"
    STRATEGY_PAUSED = "strategy_paused"
    KILL_SWITCH = "kill_switch"
    PROTECTION_MODE = "protection_mode"


def resolve_risk_control_state(
    *,
    strategy_enabled: bool,
    kill_switch_active: bool,
    protection_mode_active: bool,
) -> RiskControlState:
    """Resolve the effective control state using the fixed Phase 6 priority."""
    if protection_mode_active:
        return RiskControlState.PROTECTION_MODE
    if kill_switch_active:
        return RiskControlState.KILL_SWITCH
    if not strategy_enabled:
        return RiskControlState.STRATEGY_PAUSED
    return RiskControlState.NORMAL


@dataclass(frozen=True, slots=True)
class PreTradeRiskPolicy:
    """Configuration for the Phase 6A pre-trade risk gate."""

    max_single_symbol_notional_cny: Decimal = Decimal("200000")
    max_total_open_notional_cny: Decimal = Decimal("500000")
    min_order_notional_cny: Decimal = Decimal("1000")
    market_stale_threshold_seconds: int = 120
    duplicate_window_seconds: int = 60

    def __post_init__(self) -> None:
        if self.max_single_symbol_notional_cny <= 0:
            raise ValueError("max_single_symbol_notional_cny must be positive")
        if self.max_total_open_notional_cny <= 0:
            raise ValueError("max_total_open_notional_cny must be positive")
        if self.min_order_notional_cny <= 0:
            raise ValueError("min_order_notional_cny must be positive")
        if self.market_stale_threshold_seconds <= 0:
            raise ValueError("market_stale_threshold_seconds must be positive")
        if self.duplicate_window_seconds <= 0:
            raise ValueError("duplicate_window_seconds must be positive")


@dataclass(frozen=True, slots=True)
class PreTradeRiskContext:
    """All inputs needed to evaluate one candidate order submission."""

    signal: Signal
    decision_price: Decimal | None
    received_at: datetime
    symbol_rule: AshareSymbolRule | None = None
    market_context: MarketStateSnapshot | None = None
    current_position: Position | None = None
    open_positions: Sequence[Position] = ()
    recent_active_order_intents: Sequence[OrderIntent] = ()
    plan: SignalOrderIntentPlan | None = None
    order_type: OrderType = OrderType.MARKET
    price: Decimal | None = None
    control_state: RiskControlState = RiskControlState.NORMAL


class PreTradeRiskResult(DomainModel):
    """Structured allow/reject result suitable for logs and APIs."""

    risk_decision: RiskDecision
    reason_code: str
    reason_message: str
    rule_name: str
    details: dict[str, Any] = Field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.risk_decision is RiskDecision.ALLOW

    @classmethod
    def allow(
        cls,
        *,
        reason_code: str = "ALLOWED",
        reason_message: str = "Pre-trade risk checks passed.",
        rule_name: str = "pre_trade_risk_gate",
        details: dict[str, Any] | None = None,
    ) -> PreTradeRiskResult:
        return cls(
            risk_decision=RiskDecision.ALLOW,
            reason_code=reason_code,
            reason_message=reason_message,
            rule_name=rule_name,
            details=details or {},
        )

    @classmethod
    def reject(
        cls,
        *,
        reason_code: str,
        reason_message: str,
        rule_name: str,
        details: dict[str, Any] | None = None,
    ) -> PreTradeRiskResult:
        return cls(
            risk_decision=RiskDecision.REJECT,
            reason_code=reason_code,
            reason_message=reason_message,
            rule_name=rule_name,
            details=details or {},
        )


class PreTradeRiskGate:
    """Evaluate the fixed Phase 6A risk rules in one deterministic sequence."""

    def __init__(self, *, policy: PreTradeRiskPolicy | None = None) -> None:
        self._policy = policy or PreTradeRiskPolicy()

    @property
    def policy(self) -> PreTradeRiskPolicy:
        return self._policy

    def evaluate(self, context: PreTradeRiskContext) -> PreTradeRiskResult:
        decision_price = context.decision_price
        if decision_price is None or decision_price <= 0:
            return PreTradeRiskResult.reject(
                reason_code="INVALID_DECISION_PRICE",
                reason_message="decision_price must be present and positive for pre-trade risk.",
                rule_name="decision_price",
                details={"decision_price": decision_price},
            )

        if context.symbol_rule is None:
            return PreTradeRiskResult.reject(
                reason_code="SYMBOL_RULE_MISSING",
                reason_message="Supported A-share symbols must provide explicit trading rules.",
                rule_name="symbol_rule",
                details={"symbol": context.signal.symbol},
            )

        plan = context.plan
        if plan is not None and not plan.actionable:
            return self._decision_for_non_actionable_plan(context=context, plan=plan)

        market_context = context.market_context
        if market_context is None:
            if context.order_type is OrderType.LIMIT:
                return PreTradeRiskResult.reject(
                    reason_code="LIMIT_REQUIRES_MARKET_STATE",
                    reason_message="LIMIT orders require minimum market state in A-share V1.",
                    rule_name="market_state",
                    details={"order_type": context.order_type.value},
                )
            return PreTradeRiskResult.reject(
                reason_code="MARKET_STATE_REQUIRED",
                reason_message="Pre-trade risk requires minimum market state for A-share checks.",
                rule_name="market_state",
                details={"order_type": context.order_type.value},
            )

        stale_threshold_seconds = max(
            int((timeframe_to_timedelta(context.signal.timeframe) * 2).total_seconds()),
            self._policy.market_stale_threshold_seconds,
        )
        market_age_seconds = int(
            max((context.received_at - context.signal.event_time).total_seconds(), 0)
        )
        if market_age_seconds > stale_threshold_seconds:
            return PreTradeRiskResult.reject(
                reason_code="MARKET_DATA_STALE",
                reason_message="Latest final market data is too stale for order submission.",
                rule_name="market_staleness",
                details={
                    "signal_event_time": context.signal.event_time.isoformat(),
                    "received_at": context.received_at.isoformat(),
                    "market_age_seconds": market_age_seconds,
                    "max_allowed_age_seconds": stale_threshold_seconds,
                },
            )

        if market_context.suspension_status is not SuspensionStatus.ACTIVE:
            return PreTradeRiskResult.reject(
                reason_code="SECURITY_SUSPENDED",
                reason_message="Suspended symbols cannot pass the pre-trade risk gate.",
                rule_name="suspension",
                details={
                    "suspension_status": market_context.suspension_status.value,
                    "symbol": context.signal.symbol,
                },
            )

        if market_context.trading_phase is not TradingPhase.CONTINUOUS_AUCTION:
            return PreTradeRiskResult.reject(
                reason_code="TRADING_SESSION_UNSUPPORTED",
                reason_message="V1 only supports continuous-auction order submission.",
                rule_name="trading_phase",
                details={"trading_phase": market_context.trading_phase.value},
            )

        if plan is None:
            return PreTradeRiskResult.reject(
                reason_code="ORDER_PLAN_MISSING",
                reason_message="A normalized order plan is required before submission.",
                rule_name="plan_construction",
            )

        control_decision = self._check_control_state(context=context, plan=plan)
        if control_decision is not None:
            return control_decision

        quantity_decision = self._check_quantity_rules(context=context, plan=plan)
        if quantity_decision is not None:
            return quantity_decision

        price_decision = self._check_price_rules(context=context, plan=plan)
        if price_decision is not None:
            return price_decision

        order_notional = plan.qty * decision_price
        if order_notional < self._policy.min_order_notional_cny:
            return PreTradeRiskResult.reject(
                reason_code="MIN_ORDER_NOTIONAL_NOT_MET",
                reason_message="Order notional is below the configured pre-trade minimum.",
                rule_name="min_order_notional",
                details={
                    "order_notional": order_notional,
                    "minimum_required": self._policy.min_order_notional_cny,
                },
            )

        duplicate_decision = self._check_duplicates(context=context, plan=plan)
        if duplicate_decision is not None:
            return duplicate_decision

        max_notional_decision = self._check_notional_limits(context=context, plan=plan)
        if max_notional_decision is not None:
            return max_notional_decision

        return PreTradeRiskResult.allow(
            details={
                "symbol": context.signal.symbol,
                "side": plan.side.value if plan.side is not None else None,
                "qty": plan.qty,
                "control_state": context.control_state.value,
            }
        )

    def _decision_for_non_actionable_plan(
        self,
        *,
        context: PreTradeRiskContext,
        plan: SignalOrderIntentPlan,
    ) -> PreTradeRiskResult:
        if plan.skip_reason == "target_position_already_satisfied":
            return PreTradeRiskResult.allow(
                reason_code="TARGET_POSITION_ALREADY_SATISFIED",
                reason_message=(
                    "No order is needed because the target position is already satisfied."
                ),
                rule_name="target_position_sync",
                details={
                    "target_position": plan.target_position,
                    "current_position_qty": plan.current_position_qty,
                },
            )

        if plan.skip_reason == "sellable_qty_exhausted":
            return PreTradeRiskResult.reject(
                reason_code="SELLABLE_QTY_EXCEEDED",
                reason_message="No sellable inventory is available under the A-share T+1 contract.",
                rule_name="sellable_qty",
                details={
                    "current_position_qty": plan.current_position_qty,
                    "sellable_qty": plan.current_sellable_qty,
                    "raw_delta_qty": plan.raw_delta_qty,
                },
            )

        if plan.skip_reason == "normalized_buy_qty_below_min_qty":
            return PreTradeRiskResult.reject(
                reason_code="MIN_ORDER_QTY_NOT_MET",
                reason_message="Normalized BUY quantity is below the A-share minimum order size.",
                rule_name="min_qty",
                details={
                    "raw_delta_qty": plan.raw_delta_qty,
                    "minimum_qty": context.symbol_rule.min_qty if context.symbol_rule else None,
                },
            )

        if plan.skip_reason == "normalized_sell_qty_below_min_qty":
            if self._odd_lot_context(context=context, plan=plan):
                return PreTradeRiskResult.reject(
                    reason_code="ODD_LOT_SELL_RULE_VIOLATION",
                    reason_message=(
                        "Odd-lot inventory may only be sold as a one-shot full odd-lot order "
                        "when the symbol rule allows it."
                    ),
                    rule_name="odd_lot_sell",
                    details={
                        "sellable_qty": plan.current_sellable_qty,
                        "requested_reduction_qty": abs(plan.raw_delta_qty),
                        "allow_odd_lot_sell": (
                            context.symbol_rule.allow_odd_lot_sell
                            if context.symbol_rule is not None
                            else None
                        ),
                    },
                )

            return PreTradeRiskResult.reject(
                reason_code="MIN_ORDER_QTY_NOT_MET",
                reason_message="Normalized SELL quantity is below the A-share minimum order size.",
                rule_name="min_qty",
                details={
                    "raw_delta_qty": plan.raw_delta_qty,
                    "minimum_qty": context.symbol_rule.min_qty if context.symbol_rule else None,
                },
            )

        return PreTradeRiskResult.reject(
            reason_code="NON_ACTIONABLE_ORDER_PLAN",
            reason_message="The candidate order plan is non-actionable and cannot be submitted.",
            rule_name="plan_construction",
            details={"skip_reason": plan.skip_reason},
        )

    def _check_control_state(
        self,
        *,
        context: PreTradeRiskContext,
        plan: SignalOrderIntentPlan,
    ) -> PreTradeRiskResult | None:
        if context.control_state not in {
            RiskControlState.KILL_SWITCH,
            RiskControlState.PROTECTION_MODE,
        }:
            return None

        if self._is_true_reduction(context=context, plan=plan):
            return None

        reason_code = (
            "KILL_SWITCH_REDUCE_ONLY"
            if context.control_state is RiskControlState.KILL_SWITCH
            else "PROTECTION_MODE_REDUCE_ONLY"
        )
        reason_message = (
            "Kill switch only allows reducing or flattening protective SELL orders."
            if context.control_state is RiskControlState.KILL_SWITCH
            else "Protection mode only allows reducing or flattening protective SELL orders."
        )
        return PreTradeRiskResult.reject(
            reason_code=reason_code,
            reason_message=reason_message,
            rule_name="control_state",
            details={
                "control_state": context.control_state.value,
                "side": plan.side.value if plan.side is not None else None,
                "qty": plan.qty,
                "current_position_qty": plan.current_position_qty,
                "sellable_qty": plan.current_sellable_qty,
                "reduce_only": plan.reduce_only,
            },
        )

    def _check_quantity_rules(
        self,
        *,
        context: PreTradeRiskContext,
        plan: SignalOrderIntentPlan,
    ) -> PreTradeRiskResult | None:
        assert context.symbol_rule is not None
        if plan.side is None or plan.qty <= 0:
            return PreTradeRiskResult.reject(
                reason_code="ORDER_QTY_INVALID",
                reason_message="Normalized order quantity must be positive.",
                rule_name="qty",
                details={"qty": plan.qty},
            )

        if not self._is_multiple(plan.qty, context.symbol_rule.qty_step):
            return PreTradeRiskResult.reject(
                reason_code="QTY_STEP_VIOLATION",
                reason_message="Order quantity must align with the configured A-share step size.",
                rule_name="qty_step",
                details={"qty": plan.qty, "qty_step": context.symbol_rule.qty_step},
            )

        if plan.side is OrderSide.BUY:
            if plan.qty < context.symbol_rule.min_qty:
                return PreTradeRiskResult.reject(
                    reason_code="MIN_ORDER_QTY_NOT_MET",
                    reason_message="BUY quantity is below the configured A-share minimum.",
                    rule_name="min_qty",
                    details={"qty": plan.qty, "minimum_qty": context.symbol_rule.min_qty},
                )
            return None

        if plan.qty > plan.current_sellable_qty:
            return PreTradeRiskResult.reject(
                reason_code="SELLABLE_QTY_EXCEEDED",
                reason_message="SELL quantity cannot exceed current sellable_qty in A-share V1.",
                rule_name="sellable_qty",
                details={"qty": plan.qty, "sellable_qty": plan.current_sellable_qty},
            )

        if self._odd_lot_context(context=context, plan=plan):
            if not plan.odd_lot_sell:
                return PreTradeRiskResult.reject(
                    reason_code="ODD_LOT_SELL_RULE_VIOLATION",
                    reason_message=(
                        "Odd-lot inventory may only be sold as a one-shot full odd-lot order "
                        "when the symbol rule allows it."
                    ),
                    rule_name="odd_lot_sell",
                    details={
                        "qty": plan.qty,
                        "sellable_qty": plan.current_sellable_qty,
                        "allow_odd_lot_sell": context.symbol_rule.allow_odd_lot_sell,
                    },
                )
            return None

        if plan.qty < context.symbol_rule.min_qty:
            return PreTradeRiskResult.reject(
                reason_code="MIN_ORDER_QTY_NOT_MET",
                reason_message="SELL quantity is below the configured A-share minimum.",
                rule_name="min_qty",
                details={"qty": plan.qty, "minimum_qty": context.symbol_rule.min_qty},
            )
        return None

    def _check_price_rules(
        self,
        *,
        context: PreTradeRiskContext,
        plan: SignalOrderIntentPlan,
    ) -> PreTradeRiskResult | None:
        assert context.symbol_rule is not None
        assert context.market_context is not None
        decision_price = context.decision_price
        assert decision_price is not None

        if context.order_type is OrderType.LIMIT:
            if context.price is None or context.price <= 0:
                return PreTradeRiskResult.reject(
                    reason_code="LIMIT_PRICE_REQUIRED",
                    reason_message="LIMIT orders must provide a positive limit price.",
                    rule_name="limit_price",
                    details={"price": context.price},
                )
            if not self._is_multiple(context.price, context.symbol_rule.price_tick):
                return PreTradeRiskResult.reject(
                    reason_code="PRICE_TICK_VIOLATION",
                    reason_message="LIMIT price must align with the configured A-share tick size.",
                    rule_name="price_tick",
                    details={
                        "price": context.price,
                        "price_tick": context.symbol_rule.price_tick,
                    },
                )
            reference_price = context.price
        else:
            reference_price = decision_price

        if not self._price_within_limits(reference_price, context.market_context):
            return PreTradeRiskResult.reject(
                reason_code="PRICE_LIMIT_EXCEEDED",
                reason_message="Order price is outside the A-share daily price limits.",
                rule_name="price_limit",
                details={
                    "price": reference_price,
                    "lower_limit_price": context.market_context.lower_limit_price,
                    "upper_limit_price": context.market_context.upper_limit_price,
                    "order_type": context.order_type.value,
                },
            )

        return None

    def _check_duplicates(
        self,
        *,
        context: PreTradeRiskContext,
        plan: SignalOrderIntentPlan,
    ) -> PreTradeRiskResult | None:
        if plan.side is None:
            return None

        for existing_intent in context.recent_active_order_intents:
            if existing_intent.signal_id == context.signal.id:
                continue
            if existing_intent.account_id != context.signal.account_id:
                continue
            if existing_intent.exchange != context.signal.exchange:
                continue
            if existing_intent.symbol != context.signal.symbol:
                continue
            if existing_intent.side != plan.side:
                continue
            if existing_intent.order_type != context.order_type:
                continue
            if existing_intent.qty != plan.qty:
                continue
            if existing_intent.price != context.price:
                continue
            if existing_intent.decision_price != context.decision_price:
                continue
            if existing_intent.reduce_only != plan.reduce_only:
                continue

            return PreTradeRiskResult.reject(
                reason_code="DUPLICATE_ORDER_INTENT",
                reason_message=(
                    "A matching active order intent already exists within the duplicate window."
                ),
                rule_name="duplicate_order_intent",
                details={
                    "existing_order_intent_id": existing_intent.id,
                    "duplicate_window_seconds": self._policy.duplicate_window_seconds,
                },
            )
        return None

    def _check_notional_limits(
        self,
        *,
        context: PreTradeRiskContext,
        plan: SignalOrderIntentPlan,
    ) -> PreTradeRiskResult | None:
        decision_price = context.decision_price
        assert decision_price is not None
        if plan.side is None:
            return None

        current_qty = plan.current_position_qty
        resulting_qty = (
            current_qty + plan.qty if plan.side is OrderSide.BUY else current_qty - plan.qty
        )
        resulting_qty = max(resulting_qty, Decimal("0"))
        resulting_notional = abs(resulting_qty) * decision_price
        if resulting_notional > self._policy.max_single_symbol_notional_cny:
            return PreTradeRiskResult.reject(
                reason_code="MAX_POSITION_EXCEEDED",
                reason_message=(
                    "Resulting symbol exposure exceeds the configured maximum position notional."
                ),
                rule_name="max_single_symbol_notional",
                details={
                    "symbol": context.signal.symbol,
                    "resulting_position_qty": resulting_qty,
                    "decision_price": decision_price,
                    "resulting_notional": resulting_notional,
                    "maximum_allowed": self._policy.max_single_symbol_notional_cny,
                },
            )

        account_notional = Decimal("0")
        target_symbol_seen = False
        for position in context.open_positions:
            if position.qty <= 0:
                continue

            if position.symbol == context.signal.symbol:
                target_symbol_seen = True
                if resulting_qty > 0:
                    account_notional += resulting_notional
                continue

            reference_price = position.mark_price or position.avg_entry_price
            if reference_price is None:
                return PreTradeRiskResult.reject(
                    reason_code="POSITION_REFERENCE_PRICE_MISSING",
                    reason_message=(
                        "Existing open positions require mark_price or avg_entry_price for "
                        "account notional checks."
                    ),
                    rule_name="max_total_open_notional",
                    details={"symbol": position.symbol},
                )
            account_notional += abs(position.qty) * reference_price

        if not target_symbol_seen and resulting_qty > 0:
            account_notional += resulting_notional

        if account_notional > self._policy.max_total_open_notional_cny:
            return PreTradeRiskResult.reject(
                reason_code="MAX_OPEN_NOTIONAL_EXCEEDED",
                reason_message="Account open-position notional exceeds the configured limit.",
                rule_name="max_total_open_notional",
                details={
                    "account_open_notional": account_notional,
                    "maximum_allowed": self._policy.max_total_open_notional_cny,
                },
            )

        return None

    def _odd_lot_context(
        self,
        *,
        context: PreTradeRiskContext,
        plan: SignalOrderIntentPlan,
    ) -> bool:
        assert context.symbol_rule is not None
        return (
            plan.raw_delta_qty < 0
            and Decimal("0") < plan.current_sellable_qty < context.symbol_rule.lot_size
        )

    def _is_true_reduction(
        self,
        *,
        context: PreTradeRiskContext,
        plan: SignalOrderIntentPlan,
    ) -> bool:
        if plan.side is not OrderSide.SELL:
            return False

        current_qty = (
            context.current_position.qty if context.current_position is not None else Decimal("0")
        )
        current_sellable_qty = (
            context.current_position.sellable_qty
            if context.current_position is not None
            else Decimal("0")
        )
        if current_qty <= 0:
            return False
        if plan.qty > current_sellable_qty:
            return False

        resulting_qty = max(current_qty - plan.qty, Decimal("0"))
        return resulting_qty < current_qty

    def _price_within_limits(
        self,
        price: Decimal,
        market_context: MarketStateSnapshot,
    ) -> bool:
        return market_context.lower_limit_price <= price <= market_context.upper_limit_price

    def _is_multiple(self, value: Decimal, step: Decimal) -> bool:
        if step <= 0:
            return False
        return (value / step).to_integral_value() * step == value
