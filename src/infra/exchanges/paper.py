"""Paper execution adapter for the A-share V1 OMS flow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from src.config.settings import PaperCostModel
from src.domain.execution import (
    AshareExecutionCostBreakdown,
    ExecutionReport,
    Fill,
    FillEvent,
    LiquidityType,
    Order,
    OrderIntent,
    OrderSide,
    OrderStatus,
    OrderType,
    OrderUpdate,
)
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.shared.types import shanghai_now

FEE_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class PaperFillSlice:
    """One deterministic simulated fill slice inside a paper execution report."""

    qty: Decimal
    price: Decimal | None = None
    liquidity_type: LiquidityType = LiquidityType.TAKER


@dataclass(frozen=True, slots=True)
class PaperExecutionScenario:
    """A high-level scenario that the adapter expands into standard events."""

    fill_slices: tuple[PaperFillSlice, ...] = ()
    cancel_remaining: bool = False
    reject_code: str | None = None
    reject_message: str | None = None

    @property
    def rejected(self) -> bool:
        return self.reject_code is not None or self.reject_message is not None


class PaperScenarioResolver(Protocol):
    """Inject custom deterministic scenarios without changing OMS logic."""

    def __call__(self, order: Order, order_intent: OrderIntent) -> PaperExecutionScenario: ...


class PaperExecutionAdapter:
    """Simulate a minimal A-share paper venue for Phase 5B."""

    def __init__(
        self,
        *,
        cost_model: PaperCostModel,
        clock: Callable[[], datetime] = shanghai_now,
        scenario_resolver: PaperScenarioResolver | None = None,
    ) -> None:
        self._cost_model = cost_model
        self._clock = clock
        self._scenario_resolver = scenario_resolver

    async def submit_order(self, order: Order, order_intent: OrderIntent) -> ExecutionReport:
        """Simulate one submission and emit normalized order/fill events."""
        base_time = self._clock()
        self._validate_order_pair(order=order, order_intent=order_intent)

        reject_report = self._validate_a_share_contract(
            order=order,
            order_intent=order_intent,
            base_time=base_time,
        )
        if reject_report is not None:
            return reject_report

        scenario = (
            self._scenario_resolver(order, order_intent)
            if self._scenario_resolver is not None
            else self._default_scenario(order, order_intent)
        )
        return self._build_execution_report(
            order=order,
            order_intent=order_intent,
            scenario=scenario,
            base_time=base_time,
        )

    async def cancel_order(self, order: Order) -> ExecutionReport:
        """Emit a standard cancel update for active paper orders."""
        if order.status not in {
            OrderStatus.NEW,
            OrderStatus.ACK,
            OrderStatus.PARTIALLY_FILLED,
        }:
            return ExecutionReport(source="paper_execution")

        event_time = self._clock()
        return ExecutionReport(
            source="paper_execution",
            order_updates=(
                OrderUpdate(
                    id=self._order_update_id(order.id, "cancel"),
                    order_id=order.id,
                    order_intent_id=order.order_intent_id,
                    trader_run_id=order.trader_run_id,
                    account_id=order.account_id,
                    exchange=order.exchange,
                    symbol=order.symbol,
                    status=OrderStatus.CANCELED,
                    exchange_order_id=order.exchange_order_id,
                    filled_qty=order.filled_qty,
                    avg_fill_price=order.avg_fill_price,
                    event_time=event_time,
                    created_at=event_time,
                ),
            ),
        )

    def _validate_order_pair(self, *, order: Order, order_intent: OrderIntent) -> None:
        if order.order_intent_id != order_intent.id:
            raise ValueError("order.order_intent_id must match order_intent.id")
        if order.trader_run_id != order_intent.trader_run_id:
            raise ValueError("order.trader_run_id must match order_intent.trader_run_id")
        if order.account_id != order_intent.account_id:
            raise ValueError("order.account_id must match order_intent.account_id")
        if order.exchange != order_intent.exchange:
            raise ValueError("order.exchange must match order_intent.exchange")
        if order.symbol != order_intent.symbol:
            raise ValueError("order.symbol must match order_intent.symbol")
        if order.side != order_intent.side:
            raise ValueError("order.side must match order_intent.side")
        if order.order_type != order_intent.order_type:
            raise ValueError("order.order_type must match order_intent.order_type")

    def _validate_a_share_contract(
        self,
        *,
        order: Order,
        order_intent: OrderIntent,
        base_time: datetime,
    ) -> ExecutionReport | None:
        market_state = order_intent.market_state
        if market_state is None:
            return self._reject_report(
                order=order,
                base_time=base_time,
                code="MARKET_STATE_REQUIRED",
                message="Paper execution requires minimum market state in A-share V1.",
            )

        if market_state.suspension_status is not SuspensionStatus.ACTIVE:
            return self._reject_report(
                order=order,
                base_time=base_time,
                code="SYMBOL_SUSPENDED",
                message="Suspended symbols cannot be executed by the paper adapter.",
            )

        if market_state.trading_phase is not TradingPhase.CONTINUOUS_AUCTION:
            return self._reject_report(
                order=order,
                base_time=base_time,
                code="UNSUPPORTED_TRADING_PHASE",
                message="Phase 5B only supports continuous-auction paper execution.",
            )

        if order.order_type is OrderType.MARKET:
            execution_price = order_intent.decision_price
            assert execution_price is not None
            if not self._price_within_limits(execution_price, market_state):
                return self._reject_report(
                    order=order,
                    base_time=base_time,
                    code="DECISION_PRICE_OUT_OF_BAND",
                    message="decision_price is outside the A-share daily price limits.",
                )
            return None

        assert order.price is not None
        if not self._price_within_limits(order.price, market_state):
            return self._reject_report(
                order=order,
                base_time=base_time,
                code="LIMIT_PRICE_OUT_OF_BAND",
                message="LIMIT price is outside the A-share daily price limits.",
            )

        reference_price = order_intent.decision_price or order.price
        if not self._limit_order_is_marketable(
            side=order.side,
            limit_price=order.price,
            reference_price=reference_price,
        ):
            return self._reject_report(
                order=order,
                base_time=base_time,
                code="RESTING_LIMIT_NOT_SUPPORTED",
                message="Phase 5B does not keep resting LIMIT orders in the paper adapter.",
            )
        return None

    def _default_scenario(
        self,
        order: Order,
        order_intent: OrderIntent,
    ) -> PaperExecutionScenario:
        execution_price = order_intent.decision_price
        if order.order_type is OrderType.LIMIT:
            execution_price = order.price

        return PaperExecutionScenario(
            fill_slices=(PaperFillSlice(qty=order.qty, price=execution_price),),
        )

    def _build_execution_report(
        self,
        *,
        order: Order,
        order_intent: OrderIntent,
        scenario: PaperExecutionScenario,
        base_time: datetime,
    ) -> ExecutionReport:
        if scenario.rejected:
            return self._reject_report(
                order=order,
                base_time=base_time,
                code=scenario.reject_code or "PAPER_REJECTED",
                message=scenario.reject_message or "Paper execution scenario rejected the order.",
            )

        default_fill_price = (
            order_intent.decision_price if order.order_type is OrderType.MARKET else order.price
        )
        assert default_fill_price is not None

        exchange_order_id = self._exchange_order_id(order.id)
        order_updates = [
            OrderUpdate(
                id=self._order_update_id(order.id, "ack"),
                order_id=order.id,
                order_intent_id=order.order_intent_id,
                trader_run_id=order.trader_run_id,
                account_id=order.account_id,
                exchange=order.exchange,
                symbol=order.symbol,
                status=OrderStatus.ACK,
                exchange_order_id=exchange_order_id,
                event_time=base_time,
                created_at=base_time,
            )
        ]
        fill_events: list[FillEvent] = []
        cumulative_qty = Decimal("0")
        cumulative_notional = Decimal("0")
        event_index = 1

        for fill_index, fill_slice in enumerate(scenario.fill_slices, start=1):
            if fill_slice.qty <= 0:
                raise ValueError("Paper fill slices must carry positive qty.")

            cumulative_qty += fill_slice.qty
            if cumulative_qty > order.qty:
                raise ValueError("Paper fill slices cannot exceed order.qty.")

            fill_price = fill_slice.price or default_fill_price
            fill_time = base_time + timedelta(seconds=event_index)
            event_index += 1
            cumulative_notional += fill_slice.qty * fill_price
            avg_fill_price = cumulative_notional / cumulative_qty

            cost_breakdown = self._build_cost_breakdown(
                side=order.side,
                qty=fill_slice.qty,
                price=fill_price,
            )
            fill = Fill(
                id=self._fill_id(order.id, fill_index),
                order_id=order.id,
                trader_run_id=order.trader_run_id,
                exchange_fill_id=self._exchange_fill_id(order.id, fill_index),
                account_id=order.account_id,
                exchange=order.exchange,
                symbol=order.symbol,
                side=order.side,
                qty=fill_slice.qty,
                price=fill_price,
                fee=cost_breakdown.total_fee,
                fee_asset=cost_breakdown.currency,
                liquidity_type=fill_slice.liquidity_type,
                fill_time=fill_time,
                created_at=fill_time,
            )
            fill_events.append(
                FillEvent(
                    id=self._fill_event_id(order.id, fill_index),
                    order_id=order.id,
                    order_intent_id=order.order_intent_id,
                    trader_run_id=order.trader_run_id,
                    account_id=order.account_id,
                    exchange=order.exchange,
                    symbol=order.symbol,
                    fill=fill,
                    cost_breakdown=cost_breakdown,
                    event_time=fill_time,
                    created_at=fill_time,
                )
            )

            order_updates.append(
                OrderUpdate(
                    id=self._order_update_id(order.id, f"fill-{fill_index}"),
                    order_id=order.id,
                    order_intent_id=order.order_intent_id,
                    trader_run_id=order.trader_run_id,
                    account_id=order.account_id,
                    exchange=order.exchange,
                    symbol=order.symbol,
                    status=(
                        OrderStatus.FILLED
                        if cumulative_qty == order.qty
                        else OrderStatus.PARTIALLY_FILLED
                    ),
                    exchange_order_id=exchange_order_id,
                    filled_qty=cumulative_qty,
                    avg_fill_price=avg_fill_price,
                    event_time=fill_time,
                    created_at=fill_time,
                )
            )

        if scenario.cancel_remaining and cumulative_qty < order.qty:
            cancel_time = base_time + timedelta(seconds=event_index)
            order_updates.append(
                OrderUpdate(
                    id=self._order_update_id(order.id, "cancel_after_partial"),
                    order_id=order.id,
                    order_intent_id=order.order_intent_id,
                    trader_run_id=order.trader_run_id,
                    account_id=order.account_id,
                    exchange=order.exchange,
                    symbol=order.symbol,
                    status=OrderStatus.CANCELED,
                    exchange_order_id=exchange_order_id,
                    filled_qty=cumulative_qty,
                    avg_fill_price=(
                        None if cumulative_qty == 0 else cumulative_notional / cumulative_qty
                    ),
                    event_time=cancel_time,
                    created_at=cancel_time,
                )
            )

        return ExecutionReport(
            source="paper_execution",
            order_updates=tuple(order_updates),
            fill_events=tuple(fill_events),
        )

    def _build_cost_breakdown(
        self,
        *,
        side: OrderSide,
        qty: Decimal,
        price: Decimal,
    ) -> AshareExecutionCostBreakdown:
        gross_notional = qty * price
        commission = self._quantize_fee(gross_notional * self._cost_model.commission)
        transfer_fee = self._quantize_fee(gross_notional * self._cost_model.transfer_fee)
        stamp_duty = Decimal("0")
        if side is OrderSide.SELL:
            stamp_duty = self._quantize_fee(gross_notional * self._cost_model.stamp_duty_sell)

        total_fee = commission + transfer_fee + stamp_duty
        net_cash_flow = (
            gross_notional - total_fee if side is OrderSide.SELL else -(gross_notional + total_fee)
        )
        return AshareExecutionCostBreakdown(
            gross_notional=gross_notional,
            commission=commission,
            transfer_fee=transfer_fee,
            stamp_duty=stamp_duty,
            total_fee=total_fee,
            net_cash_flow=net_cash_flow,
        )

    def _reject_report(
        self,
        *,
        order: Order,
        base_time: datetime,
        code: str,
        message: str,
    ) -> ExecutionReport:
        return ExecutionReport(
            source="paper_execution",
            order_updates=(
                OrderUpdate(
                    id=self._order_update_id(order.id, f"reject:{code}"),
                    order_id=order.id,
                    order_intent_id=order.order_intent_id,
                    trader_run_id=order.trader_run_id,
                    account_id=order.account_id,
                    exchange=order.exchange,
                    symbol=order.symbol,
                    status=OrderStatus.REJECTED,
                    error_code=code,
                    error_message=message,
                    event_time=base_time,
                    created_at=base_time,
                ),
            ),
        )

    def _price_within_limits(self, price: Decimal, market_state: MarketStateSnapshot) -> bool:
        return market_state.lower_limit_price <= price <= market_state.upper_limit_price

    def _limit_order_is_marketable(
        self,
        *,
        side: OrderSide,
        limit_price: Decimal,
        reference_price: Decimal,
    ) -> bool:
        if side is OrderSide.BUY:
            return limit_price >= reference_price
        return limit_price <= reference_price

    def _quantize_fee(self, value: Decimal) -> Decimal:
        return value.quantize(FEE_QUANTUM, rounding=ROUND_HALF_UP)

    def _exchange_order_id(self, order_id) -> str:
        return f"paper-order-{order_id.hex[:12]}"

    def _exchange_fill_id(self, order_id, fill_index: int) -> str:
        return f"paper-fill-{order_id.hex[:12]}-{fill_index}"

    def _order_update_id(self, order_id, suffix: str):
        return uuid5(NAMESPACE_URL, f"signalark:paper-order-update:{order_id}:{suffix}")

    def _fill_id(self, order_id, fill_index: int):
        return uuid5(NAMESPACE_URL, f"signalark:paper-fill:{order_id}:{fill_index}")

    def _fill_event_id(self, order_id, fill_index: int):
        return uuid5(NAMESPACE_URL, f"signalark:paper-fill-event:{order_id}:{fill_index}")
