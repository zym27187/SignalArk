"""Persistence-first OMS application service for Phase 5A."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import or_, select
from src.config.settings import AshareSymbolRule
from src.domain.execution import (
    ExecutionReport,
    Fill,
    Order,
    OrderIntent,
    OrderIntentStatus,
    OrderType,
    SignalOrderIntentPlan,
    apply_order_update,
    build_order_id_for_intent,
    build_signal_order_intent_plan,
    create_order_from_intent,
    execution_report_is_empty,
)
from src.domain.market import MarketStateSnapshot
from src.domain.portfolio import BalanceSnapshot, Position
from src.domain.portfolio.ledger import (
    apply_fill_event_to_portfolio,
    release_position_sellable_qty,
)
from src.domain.risk import (
    PreTradeRiskContext,
    PreTradeRiskGate,
    PreTradeRiskResult,
    RiskControlState,
)
from src.domain.strategy import Signal
from src.infra.db import EventLogEntry, RecoveryState, SqlAlchemyRepositories
from src.infra.db.models import OrderIntentRecord, OrderRecord
from src.shared.types import SHANGHAI_TIMEZONE, shanghai_now

ACTIVE_ORDER_INTENT_STATUSES = (
    OrderIntentStatus.NEW.value,
    OrderIntentStatus.SUBMITTED.value,
)
ACTIVE_ORDER_STATUSES = (
    "NEW",
    "ACK",
    "PARTIALLY_FILLED",
)


class OmsPersistencePort(Protocol):
    """Minimal persistence contract used by the trader OMS skeleton."""

    def get_position(self, *, account_id: str, exchange: str, symbol: str) -> Position | None: ...

    def save_position(self, position: Position) -> Position: ...

    def get_order(self, order_id: UUID) -> Order | None: ...

    def save_event_log(self, event_log: EventLogEntry) -> EventLogEntry: ...

    def get_fill(self, fill_id: UUID) -> Fill | None: ...

    def save_fill(self, fill: Fill) -> Fill: ...

    def get_latest_balance_snapshot(
        self,
        *,
        account_id: str,
        exchange: str,
        asset: str,
    ) -> BalanceSnapshot | None: ...

    def save_balance_snapshot(self, balance_snapshot: BalanceSnapshot) -> BalanceSnapshot: ...

    def save_order(self, order: Order) -> Order: ...

    def save_order_intent(self, order_intent: OrderIntent) -> OrderIntent: ...

    def list_recent_active_order_intents(
        self,
        *,
        account_id: str,
        exchange: str,
        symbol: str,
        created_after: datetime,
    ) -> tuple[OrderIntent, ...]: ...

    def save_signal(self, signal: Signal) -> Signal: ...

    def load_recovery_state(
        self,
        *,
        account_id: str,
        trader_run_id: UUID | None = None,
        event_limit: int = 100,
    ) -> RecoveryState: ...


class ExecutionGateway(Protocol):
    """Reserved async execution adapter point for Phase 5B."""

    async def submit_order(self, order: Order, order_intent: OrderIntent) -> ExecutionReport: ...

    async def cancel_order(self, order: Order) -> ExecutionReport: ...


@dataclass(slots=True)
class RepositoryBackedOmsPersistence:
    """Bridge the trader OMS service onto the SQLAlchemy repository bundle."""

    repositories: SqlAlchemyRepositories

    def save_signal(self, signal: Signal) -> Signal:
        return self.repositories.signals.save(signal)

    def get_position(self, *, account_id: str, exchange: str, symbol: str) -> Position | None:
        return self.repositories.positions.get_by_symbol(
            account_id=account_id,
            exchange=exchange,
            symbol=symbol,
        )

    def save_position(self, position: Position) -> Position:
        return self.repositories.positions.save(position)

    def save_order_intent(self, order_intent: OrderIntent) -> OrderIntent:
        return self.repositories.order_intents.save(order_intent)

    def list_recent_active_order_intents(
        self,
        *,
        account_id: str,
        exchange: str,
        symbol: str,
        created_after: datetime,
    ) -> tuple[OrderIntent, ...]:
        session = self.repositories.order_intents.session
        query = (
            select(OrderIntentRecord)
            .outerjoin(OrderRecord, OrderRecord.order_intent_id == OrderIntentRecord.id)
            .where(OrderIntentRecord.account_id == account_id)
            .where(OrderIntentRecord.exchange == exchange)
            .where(OrderIntentRecord.symbol == symbol)
            .where(OrderIntentRecord.created_at >= created_after)
            .where(OrderIntentRecord.status.in_(ACTIVE_ORDER_INTENT_STATUSES))
            .where(
                or_(
                    OrderRecord.id.is_(None),
                    OrderRecord.status.in_(ACTIVE_ORDER_STATUSES),
                )
            )
            .order_by(OrderIntentRecord.created_at.desc(), OrderIntentRecord.id.desc())
        )
        return tuple(_order_intent_from_record(record) for record in session.scalars(query))

    def save_order(self, order: Order) -> Order:
        return self.repositories.orders.save(order)

    def get_order(self, order_id: UUID) -> Order | None:
        return self.repositories.orders.get(order_id)

    def save_event_log(self, event_log: EventLogEntry) -> EventLogEntry:
        return self.repositories.event_logs.save(event_log)

    def get_fill(self, fill_id: UUID) -> Fill | None:
        return self.repositories.fills.get(fill_id)

    def save_fill(self, fill: Fill) -> Fill:
        return self.repositories.fills.save(fill)

    def get_latest_balance_snapshot(
        self,
        *,
        account_id: str,
        exchange: str,
        asset: str,
    ) -> BalanceSnapshot | None:
        recovered_state = self.repositories.recovery.load_runtime_state(
            account_id=account_id,
            event_limit=1,
        )
        for snapshot in recovered_state.latest_balance_snapshots:
            if snapshot.exchange == exchange and snapshot.asset == asset:
                return snapshot
        return None

    def save_balance_snapshot(self, balance_snapshot: BalanceSnapshot) -> BalanceSnapshot:
        return self.repositories.balance_snapshots.save(balance_snapshot)

    def load_recovery_state(
        self,
        *,
        account_id: str,
        trader_run_id: UUID | None = None,
        event_limit: int = 100,
    ) -> RecoveryState:
        return self.repositories.recovery.load_runtime_state(
            account_id=account_id,
            trader_run_id=trader_run_id,
            event_limit=event_limit,
        )


class NoopExecutionGateway:
    """No-op adapter used until Phase 5B lands paper execution details."""

    async def submit_order(self, order: Order, order_intent: OrderIntent) -> ExecutionReport:
        return ExecutionReport()

    async def cancel_order(self, order: Order) -> ExecutionReport:
        return ExecutionReport()


def _shanghai_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=SHANGHAI_TIMEZONE)
    return value.astimezone(SHANGHAI_TIMEZONE)


def _order_intent_from_record(record: OrderIntentRecord) -> OrderIntent:
    return OrderIntent(
        id=record.id,
        signal_id=record.signal_id,
        strategy_id=record.strategy_id,
        trader_run_id=record.trader_run_id,
        account_id=record.account_id,
        exchange=record.exchange,
        symbol=record.symbol,
        side=record.side,
        order_type=record.order_type,
        time_in_force=record.time_in_force,
        qty=record.qty,
        price=record.price,
        decision_price=record.decision_price,
        reduce_only=record.reduce_only,
        market_context_json=record.market_context_json,
        idempotency_key=record.idempotency_key,
        status=record.status,
        risk_decision=record.risk_decision,
        risk_reason=record.risk_reason,
        created_at=_shanghai_datetime(record.created_at),
    )


@dataclass(frozen=True, slots=True)
class OmsSubmission:
    """The persisted OMS objects produced by one signal-handling attempt."""

    signal: Signal
    plan: SignalOrderIntentPlan
    order_intent: OrderIntent
    order: Order


class TraderOmsService:
    """Persist order intents before invoking any execution adapter."""

    def __init__(
        self,
        persistence: OmsPersistencePort,
        *,
        execution_gateway: ExecutionGateway | None = None,
        risk_gate: PreTradeRiskGate | None = None,
    ) -> None:
        self._persistence = persistence
        self._execution_gateway = execution_gateway or NoopExecutionGateway()
        self._risk_gate = risk_gate or PreTradeRiskGate()

    async def submit_signal(
        self,
        *,
        signal: Signal,
        symbol_rule: AshareSymbolRule | None,
        decision_price: Decimal | None,
        market_context: MarketStateSnapshot | None,
        current_position: Position | None = None,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal | None = None,
        control_state: RiskControlState = RiskControlState.NORMAL,
        received_at: datetime | None = None,
    ) -> OmsSubmission | None:
        """Persist Signal -> OrderIntent -> Order before execution handoff."""
        occurred_at = received_at or shanghai_now()
        persisted_signal = self._persistence.save_signal(signal)
        resolved_position = current_position or self._persistence.get_position(
            account_id=signal.account_id,
            exchange=signal.exchange,
            symbol=signal.symbol,
        )
        if market_context is not None:
            resolved_position = self._release_position_for_trade_date(
                position=resolved_position,
                effective_trade_date=market_context.trade_date,
                occurred_at=occurred_at,
                trader_run_id=persisted_signal.trader_run_id,
            )

        plan: SignalOrderIntentPlan | None = None
        if (
            market_context is not None
            and symbol_rule is not None
            and decision_price is not None
            and decision_price > 0
        ):
            plan = build_signal_order_intent_plan(
                signal=persisted_signal,
                symbol_rule=symbol_rule,
                current_position=resolved_position,
                decision_price=decision_price,
                market_context=market_context,
                order_type=order_type,
                price=price,
            )

        open_positions = ()
        recent_active_order_intents = ()
        if plan is not None and plan.actionable:
            open_positions = self._persistence.load_recovery_state(
                account_id=persisted_signal.account_id,
                event_limit=0,
            ).open_positions
            recent_active_order_intents = self._persistence.list_recent_active_order_intents(
                account_id=persisted_signal.account_id,
                exchange=persisted_signal.exchange,
                symbol=persisted_signal.symbol,
                created_after=occurred_at
                - timedelta(seconds=self._risk_gate.policy.duplicate_window_seconds),
            )

        risk_result = self._risk_gate.evaluate(
            PreTradeRiskContext(
                signal=persisted_signal,
                decision_price=decision_price,
                received_at=occurred_at,
                symbol_rule=symbol_rule,
                market_context=market_context,
                current_position=resolved_position,
                open_positions=open_positions,
                recent_active_order_intents=recent_active_order_intents,
                plan=plan,
                order_type=order_type,
                price=price,
                control_state=control_state,
            )
        )
        if not risk_result.allowed:
            self._persist_risk_rejection(
                signal=persisted_signal,
                risk_result=risk_result,
                occurred_at=occurred_at,
                current_position=resolved_position,
                market_context=market_context,
                order_type=order_type,
                price=price,
                decision_price=decision_price,
                control_state=control_state,
                plan=plan,
            )
            return None

        if plan is None or not plan.actionable:
            self._persist_event(
                event_type="oms.signal_skipped",
                related_object_type="signal",
                related_object_id=persisted_signal.id,
                trader_run_id=persisted_signal.trader_run_id,
                account_id=persisted_signal.account_id,
                exchange=persisted_signal.exchange,
                symbol=persisted_signal.symbol,
                occurred_at=occurred_at,
                payload={
                    "skip_reason": plan.skip_reason if plan is not None else "no_order_plan",
                    "risk_result": risk_result,
                    "target_position": persisted_signal.target_position,
                    "current_position_qty": (
                        plan.current_position_qty
                        if plan is not None
                        else (
                            resolved_position.qty if resolved_position is not None else Decimal("0")
                        )
                    ),
                    "current_sellable_qty": (
                        plan.current_sellable_qty
                        if plan is not None
                        else (
                            resolved_position.sellable_qty
                            if resolved_position is not None
                            else Decimal("0")
                        )
                    ),
                    "decision_price": decision_price,
                    "market_context": market_context,
                },
            )
            return None

        order_intent = plan.to_order_intent(created_at=occurred_at)
        persisted_intent = self._persistence.save_order_intent(order_intent)

        order_id = build_order_id_for_intent(persisted_intent.id)
        if persisted_intent.status is OrderIntentStatus.SUBMITTED:
            existing_order = self._persistence.get_order(order_id)
            if existing_order is None:
                existing_order = self._persistence.save_order(
                    create_order_from_intent(
                        persisted_intent,
                        order_id=order_id,
                        submitted_at=occurred_at,
                    )
                )
            return OmsSubmission(
                signal=persisted_signal,
                plan=plan,
                order_intent=persisted_intent,
                order=existing_order,
            )

        self._persist_event(
            event_type="oms.order_intent_persisted",
            related_object_type="order_intent",
            related_object_id=persisted_intent.id,
            trader_run_id=persisted_signal.trader_run_id,
            account_id=persisted_signal.account_id,
            exchange=persisted_signal.exchange,
            symbol=persisted_signal.symbol,
            occurred_at=occurred_at,
            payload={
                "signal_id": persisted_signal.id,
                "target_position": persisted_signal.target_position,
                "current_position_qty": plan.current_position_qty,
                "current_sellable_qty": plan.current_sellable_qty,
                "raw_delta_qty": plan.raw_delta_qty,
                "order_intent_qty": plan.qty,
                "decision_price": decision_price,
                "market_context": market_context,
                "reduce_only": plan.reduce_only,
                "odd_lot_sell": plan.odd_lot_sell,
                "risk_decision": risk_result.risk_decision,
                "risk_reason_code": risk_result.reason_code,
            },
        )

        order = create_order_from_intent(
            persisted_intent,
            order_id=order_id,
            submitted_at=occurred_at,
        )
        persisted_order = self._persistence.save_order(order)

        self._persist_event(
            event_type="oms.order_persisted",
            related_object_type="order",
            related_object_id=persisted_order.id,
            trader_run_id=persisted_signal.trader_run_id,
            account_id=persisted_signal.account_id,
            exchange=persisted_signal.exchange,
            symbol=persisted_signal.symbol,
            occurred_at=occurred_at,
            payload={
                "order_intent_id": persisted_intent.id,
                "order_status": persisted_order.status,
                "qty": persisted_order.qty,
                "decision_price": decision_price,
            },
        )

        try:
            execution_report = await self._execution_gateway.submit_order(
                persisted_order,
                persisted_intent,
            )
        except Exception as exc:
            errored_order = persisted_order.model_copy(
                update={
                    "last_error_code": "SUBMIT_FAILED",
                    "last_error_message": str(exc),
                    "updated_at": occurred_at,
                }
            )
            self._persistence.save_order(errored_order)
            self._persist_event(
                event_type="oms.execution_submission_failed",
                related_object_type="order",
                related_object_id=persisted_order.id,
                trader_run_id=persisted_signal.trader_run_id,
                account_id=persisted_signal.account_id,
                exchange=persisted_signal.exchange,
                symbol=persisted_signal.symbol,
                occurred_at=occurred_at,
                payload={"order_intent_id": persisted_intent.id, "error": str(exc)},
            )
            raise

        submitted_intent = persisted_intent.model_copy(
            update={"status": OrderIntentStatus.SUBMITTED}
        )
        persisted_submitted_intent = self._persistence.save_order_intent(submitted_intent)

        self._persist_event(
            event_type="oms.execution_submission_requested",
            related_object_type="order",
            related_object_id=persisted_order.id,
            trader_run_id=persisted_signal.trader_run_id,
            account_id=persisted_signal.account_id,
            exchange=persisted_signal.exchange,
            symbol=persisted_signal.symbol,
            occurred_at=occurred_at,
            payload={
                "order_intent_id": persisted_intent.id,
                "order_status": persisted_order.status,
                "decision_price": decision_price,
                "market_context": market_context,
                "execution_source": execution_report.source,
            },
        )

        latest_order = (
            persisted_order
            if execution_report_is_empty(execution_report)
            else self._apply_execution_report(
                report=execution_report,
                initial_order=persisted_order,
            )
        )

        return OmsSubmission(
            signal=persisted_signal,
            plan=plan,
            order_intent=persisted_submitted_intent,
            order=latest_order,
        )

    async def cancel_order(
        self,
        *,
        order_id: UUID,
        received_at: datetime | None = None,
    ) -> Order | None:
        """Cancel one active order through the execution gateway."""
        occurred_at = received_at or shanghai_now()
        order = self._persistence.get_order(order_id)
        if order is None:
            return None

        execution_report = await self._execution_gateway.cancel_order(order)
        if execution_report_is_empty(execution_report):
            return order

        self._persist_event(
            event_type="oms.execution_cancel_requested",
            related_object_type="order",
            related_object_id=order.id,
            trader_run_id=order.trader_run_id,
            account_id=order.account_id,
            exchange=order.exchange,
            symbol=order.symbol,
            occurred_at=occurred_at,
            payload={"execution_source": execution_report.source},
        )
        return self._apply_execution_report(
            report=execution_report,
            initial_order=order,
        )

    def load_recovery_state(
        self,
        *,
        account_id: str,
        trader_run_id: UUID | None = None,
        event_limit: int = 100,
        effective_trade_date: date | None = None,
    ) -> RecoveryState:
        """Return the persisted OMS/portfolio state needed after restart."""
        recovered_state = self._persistence.load_recovery_state(
            account_id=account_id,
            trader_run_id=trader_run_id,
            event_limit=event_limit,
        )
        if effective_trade_date is None:
            return recovered_state

        released_at = shanghai_now()
        return RecoveryState(
            open_orders=recovered_state.open_orders,
            open_positions=tuple(
                release_position_sellable_qty(
                    position,
                    effective_trade_date=effective_trade_date,
                    released_at=released_at,
                ).position
                for position in recovered_state.open_positions
            ),
            latest_balance_snapshots=recovered_state.latest_balance_snapshots,
            recent_event_logs=recovered_state.recent_event_logs,
        )

    def _apply_execution_report(
        self,
        *,
        report: ExecutionReport,
        initial_order: Order,
    ) -> Order:
        current_order = initial_order
        for order_update in report.order_updates:
            current_order = self._persistence.save_order(
                apply_order_update(current_order, order_update)
            )
            self._persist_event(
                event_type="execution.order_updated",
                related_object_type="order",
                related_object_id=current_order.id,
                source=report.source,
                trader_run_id=current_order.trader_run_id,
                account_id=current_order.account_id,
                exchange=current_order.exchange,
                symbol=current_order.symbol,
                occurred_at=order_update.event_time,
                payload={
                    "execution_source": report.source,
                    "order_update": order_update,
                },
            )

        for fill_event in report.fill_events:
            if self._persistence.get_fill(fill_event.fill.id) is not None:
                continue

            persisted_fill = self._persistence.save_fill(fill_event.fill)
            self._persist_event(
                event_type="execution.fill_recorded",
                related_object_type="fill",
                related_object_id=persisted_fill.id,
                source=report.source,
                trader_run_id=fill_event.trader_run_id,
                account_id=fill_event.account_id,
                exchange=fill_event.exchange,
                symbol=fill_event.symbol,
                occurred_at=fill_event.event_time,
                payload={
                    "execution_source": report.source,
                    "fill_event": fill_event,
                },
            )
            portfolio_update = apply_fill_event_to_portfolio(
                fill_event,
                current_position=self._persistence.get_position(
                    account_id=fill_event.account_id,
                    exchange=fill_event.exchange,
                    symbol=fill_event.symbol,
                ),
                current_balance=self._persistence.get_latest_balance_snapshot(
                    account_id=fill_event.account_id,
                    exchange=fill_event.exchange,
                    asset=fill_event.cost_breakdown.currency,
                ),
            )
            persisted_position = self._persistence.save_position(portfolio_update.position)
            persisted_balance_snapshot = self._persistence.save_balance_snapshot(
                portfolio_update.balance_snapshot
            )
            self._persist_event(
                event_type="portfolio.position_updated",
                related_object_type="position",
                related_object_id=persisted_position.id,
                source=report.source,
                trader_run_id=fill_event.trader_run_id,
                account_id=fill_event.account_id,
                exchange=fill_event.exchange,
                symbol=fill_event.symbol,
                occurred_at=fill_event.event_time,
                payload={
                    "fill_id": persisted_fill.id,
                    "fill_side": fill_event.fill.side,
                    "fill_qty": fill_event.fill.qty,
                    "fill_price": fill_event.fill.price,
                    "released_sellable_qty": portfolio_update.released_sellable_qty,
                    "realized_pnl_delta": portfolio_update.realized_pnl_delta,
                    "position_qty": persisted_position.qty,
                    "sellable_qty": persisted_position.sellable_qty,
                    "avg_entry_price": persisted_position.avg_entry_price,
                    "mark_price": persisted_position.mark_price,
                    "realized_pnl": persisted_position.realized_pnl,
                    "unrealized_pnl": persisted_position.unrealized_pnl,
                    "cost_breakdown": fill_event.cost_breakdown,
                },
            )
            self._persist_event(
                event_type="portfolio.balance_updated",
                related_object_type="balance_snapshot",
                related_object_id=persisted_balance_snapshot.id,
                source=report.source,
                trader_run_id=fill_event.trader_run_id,
                account_id=fill_event.account_id,
                exchange=fill_event.exchange,
                symbol=fill_event.symbol,
                occurred_at=fill_event.event_time,
                payload={
                    "fill_id": persisted_fill.id,
                    "asset": persisted_balance_snapshot.asset,
                    "cash_delta": portfolio_update.cash_delta,
                    "total": persisted_balance_snapshot.total,
                    "available": persisted_balance_snapshot.available,
                    "locked": persisted_balance_snapshot.locked,
                    "cost_breakdown": fill_event.cost_breakdown,
                },
            )

        return current_order

    def _release_position_for_trade_date(
        self,
        *,
        position: Position | None,
        effective_trade_date: date,
        occurred_at: datetime,
        trader_run_id: UUID,
    ) -> Position | None:
        if position is None:
            return None

        release = release_position_sellable_qty(
            position,
            effective_trade_date=effective_trade_date,
            released_at=occurred_at,
        )
        if not release.applied:
            return position

        persisted_position = self._persistence.save_position(release.position)
        self._persist_event(
            event_type="portfolio.sellable_qty_released",
            related_object_type="position",
            related_object_id=persisted_position.id,
            trader_run_id=trader_run_id,
            account_id=persisted_position.account_id,
            exchange=persisted_position.exchange,
            symbol=persisted_position.symbol,
            occurred_at=occurred_at,
            payload={
                "effective_trade_date": str(effective_trade_date),
                "released_qty": release.released_qty,
                "qty": persisted_position.qty,
                "sellable_qty": persisted_position.sellable_qty,
            },
        )
        return persisted_position

    def _persist_risk_rejection(
        self,
        *,
        signal: Signal,
        risk_result: PreTradeRiskResult,
        occurred_at: datetime,
        current_position: Position | None,
        market_context: MarketStateSnapshot | None,
        order_type: OrderType,
        price: Decimal | None,
        decision_price: Decimal | None,
        control_state: RiskControlState,
        plan: SignalOrderIntentPlan | None,
    ) -> None:
        self._persist_event(
            event_type="oms.risk_rejected",
            related_object_type="signal",
            related_object_id=signal.id,
            trader_run_id=signal.trader_run_id,
            account_id=signal.account_id,
            exchange=signal.exchange,
            symbol=signal.symbol,
            occurred_at=occurred_at,
            payload={
                "risk_result": risk_result,
                "target_position": signal.target_position,
                "current_position_qty": (
                    plan.current_position_qty
                    if plan is not None
                    else (current_position.qty if current_position is not None else Decimal("0"))
                ),
                "current_sellable_qty": (
                    plan.current_sellable_qty
                    if plan is not None
                    else (
                        current_position.sellable_qty
                        if current_position is not None
                        else Decimal("0")
                    )
                ),
                "raw_delta_qty": plan.raw_delta_qty if plan is not None else None,
                "order_type": order_type,
                "price": price,
                "decision_price": decision_price,
                "control_state": control_state.value,
                "market_context": market_context,
            },
        )

    def _persist_event(
        self,
        *,
        event_type: str,
        related_object_type: str,
        related_object_id: UUID,
        trader_run_id: UUID,
        account_id: str,
        exchange: str,
        symbol: str,
        occurred_at: datetime,
        payload: dict[str, object],
        source: str = "trader_oms",
    ) -> None:
        self._persistence.save_event_log(
            EventLogEntry(
                event_type=event_type,
                source=source,
                trader_run_id=trader_run_id,
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
                related_object_type=related_object_type,
                related_object_id=related_object_id,
                event_time=occurred_at,
                ingest_time=occurred_at,
                created_at=occurred_at,
                payload_json=payload,
            )
        )
