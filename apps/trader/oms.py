"""Persistence-first OMS application service for Phase 5A."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import sessionmaker
from src.config import Settings
from src.config.settings import AshareSymbolRule
from src.domain.execution import (
    ExecutionReport,
    Fill,
    Order,
    OrderIntent,
    OrderIntentStatus,
    OrderStatus,
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
    PreTradeRiskPolicy,
    PreTradeRiskResult,
    RiskControlState,
)
from src.domain.strategy import Signal
from src.infra.db import EventLogEntry, RecoveryState, SqlAlchemyRepositories, session_scope
from src.infra.db.models import FillRecord, OrderIntentRecord, OrderRecord
from src.infra.exchanges import PaperExecutionAdapter
from src.infra.observability import SignalArkObservability
from src.shared.types import SHANGHAI_TIMEZONE, shanghai_now

from apps.trader.control_plane import SubmissionLeaseGuard, TraderControlPlaneStore

ACTIVE_ORDER_INTENT_STATUSES = (
    OrderIntentStatus.NEW.value,
    OrderIntentStatus.SUBMITTED.value,
)
ACTIVE_ORDER_STATUSES = (
    "NEW",
    "ACK",
    "PARTIALLY_FILLED",
)
DEFAULT_PAPER_INITIAL_CASH = Decimal("100000")
PAPER_SETTLEMENT_ASSET = "CNY"


class OmsPersistencePort(Protocol):
    """Minimal persistence contract used by the trader OMS skeleton."""

    def get_position(self, *, account_id: str, exchange: str, symbol: str) -> Position | None: ...

    def save_position(self, position: Position) -> Position: ...

    def get_order(self, order_id: UUID) -> Order | None: ...

    def save_event_log(self, event_log: EventLogEntry) -> EventLogEntry: ...

    def get_fill(self, fill_id: UUID) -> Fill | None: ...

    def save_fill(self, fill: Fill) -> Fill: ...

    def has_fill_history(self, *, account_id: str) -> bool: ...

    def get_latest_balance_snapshot(
        self,
        *,
        account_id: str,
        exchange: str,
        asset: str,
    ) -> BalanceSnapshot | None: ...

    def save_balance_snapshot(self, balance_snapshot: BalanceSnapshot) -> BalanceSnapshot: ...

    def save_order(self, order: Order) -> Order: ...

    def get_order_intent(self, order_intent_id: UUID) -> OrderIntent | None: ...

    def save_order_intent(self, order_intent: OrderIntent) -> OrderIntent: ...

    def list_active_orders(self, *, account_id: str) -> tuple[Order, ...]: ...

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

    def get_order_intent(self, order_intent_id: UUID) -> OrderIntent | None:
        return self.repositories.order_intents.get(order_intent_id)

    def list_active_orders(self, *, account_id: str) -> tuple[Order, ...]:
        session = self.repositories.orders.session
        query = (
            select(OrderRecord)
            .where(OrderRecord.account_id == account_id)
            .where(OrderRecord.status.in_(ACTIVE_ORDER_STATUSES))
            .order_by(OrderRecord.updated_at.asc(), OrderRecord.id.asc())
        )
        return tuple(_order_from_record(record) for record in session.scalars(query))

    def save_event_log(self, event_log: EventLogEntry) -> EventLogEntry:
        return self.repositories.event_logs.save(event_log)

    def get_fill(self, fill_id: UUID) -> Fill | None:
        return self.repositories.fills.get(fill_id)

    def save_fill(self, fill: Fill) -> Fill:
        return self.repositories.fills.save(fill)

    def has_fill_history(self, *, account_id: str) -> bool:
        session = self.repositories.fills.session
        query = select(FillRecord.id).where(FillRecord.account_id == account_id).limit(1)
        return session.scalar(query) is not None

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


@dataclass(slots=True)
class SessionFactoryBackedOmsPersistence:
    """Open a fresh SQLAlchemy session per OMS operation for runtime use."""

    session_factory: sessionmaker

    def _with_persistence(self, operation):
        with session_scope(self.session_factory) as session:
            persistence = RepositoryBackedOmsPersistence(
                SqlAlchemyRepositories.from_session(session)
            )
            return operation(persistence)

    def save_signal(self, signal: Signal) -> Signal:
        return self._with_persistence(lambda persistence: persistence.save_signal(signal))

    def get_position(self, *, account_id: str, exchange: str, symbol: str) -> Position | None:
        return self._with_persistence(
            lambda persistence: persistence.get_position(
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
            )
        )

    def save_position(self, position: Position) -> Position:
        return self._with_persistence(lambda persistence: persistence.save_position(position))

    def save_order_intent(self, order_intent: OrderIntent) -> OrderIntent:
        return self._with_persistence(
            lambda persistence: persistence.save_order_intent(order_intent)
        )

    def list_recent_active_order_intents(
        self,
        *,
        account_id: str,
        exchange: str,
        symbol: str,
        created_after: datetime,
    ) -> tuple[OrderIntent, ...]:
        return self._with_persistence(
            lambda persistence: persistence.list_recent_active_order_intents(
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
                created_after=created_after,
            )
        )

    def save_order(self, order: Order) -> Order:
        return self._with_persistence(lambda persistence: persistence.save_order(order))

    def get_order(self, order_id: UUID) -> Order | None:
        return self._with_persistence(lambda persistence: persistence.get_order(order_id))

    def get_order_intent(self, order_intent_id: UUID) -> OrderIntent | None:
        return self._with_persistence(
            lambda persistence: persistence.get_order_intent(order_intent_id)
        )

    def list_active_orders(self, *, account_id: str) -> tuple[Order, ...]:
        return self._with_persistence(
            lambda persistence: persistence.list_active_orders(account_id=account_id)
        )

    def save_event_log(self, event_log: EventLogEntry) -> EventLogEntry:
        return self._with_persistence(lambda persistence: persistence.save_event_log(event_log))

    def get_fill(self, fill_id: UUID) -> Fill | None:
        return self._with_persistence(lambda persistence: persistence.get_fill(fill_id))

    def save_fill(self, fill: Fill) -> Fill:
        return self._with_persistence(lambda persistence: persistence.save_fill(fill))

    def has_fill_history(self, *, account_id: str) -> bool:
        return self._with_persistence(
            lambda persistence: persistence.has_fill_history(account_id=account_id)
        )

    def get_latest_balance_snapshot(
        self,
        *,
        account_id: str,
        exchange: str,
        asset: str,
    ) -> BalanceSnapshot | None:
        return self._with_persistence(
            lambda persistence: persistence.get_latest_balance_snapshot(
                account_id=account_id,
                exchange=exchange,
                asset=asset,
            )
        )

    def save_balance_snapshot(self, balance_snapshot: BalanceSnapshot) -> BalanceSnapshot:
        return self._with_persistence(
            lambda persistence: persistence.save_balance_snapshot(balance_snapshot)
        )

    def load_recovery_state(
        self,
        *,
        account_id: str,
        trader_run_id: UUID | None = None,
        event_limit: int = 100,
    ) -> RecoveryState:
        return self._with_persistence(
            lambda persistence: persistence.load_recovery_state(
                account_id=account_id,
                trader_run_id=trader_run_id,
                event_limit=event_limit,
            )
        )


class NoopExecutionGateway:
    """No-op adapter used until Phase 5B lands paper execution details."""

    async def submit_order(self, order: Order, order_intent: OrderIntent) -> ExecutionReport:
        return ExecutionReport()

    async def cancel_order(self, order: Order) -> ExecutionReport:
        return ExecutionReport()


def build_pretrade_risk_policy(settings: Settings) -> PreTradeRiskPolicy:
    """Project Settings -> Phase 6A risk policy translation."""
    return PreTradeRiskPolicy(
        max_single_symbol_notional_cny=settings.max_single_symbol_notional_cny,
        max_total_open_notional_cny=settings.max_total_open_notional_cny,
        min_order_notional_cny=settings.min_order_notional_cny,
        market_stale_threshold_seconds=settings.market_stale_threshold_seconds,
    )


def build_default_trader_oms_service(
    *,
    settings: Settings,
    session_factory: sessionmaker,
    control_store: TraderControlPlaneStore | None = None,
    observability: SignalArkObservability | None = None,
    execution_gateway: ExecutionGateway | None = None,
) -> TraderOmsService:
    """Build the runtime OMS service with settings-backed risk limits."""
    resolved_gateway = execution_gateway or PaperExecutionAdapter(
        cost_model=settings.paper_cost_model
    )
    return TraderOmsService(
        SessionFactoryBackedOmsPersistence(session_factory),
        execution_gateway=resolved_gateway,
        risk_gate=PreTradeRiskGate(policy=build_pretrade_risk_policy(settings)),
        control_store=control_store,
        observability=observability,
        paper_initial_cash=settings.paper_initial_cash,
    )


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


def _order_from_record(record: OrderRecord) -> Order:
    return Order(
        id=record.id,
        order_intent_id=record.order_intent_id,
        trader_run_id=record.trader_run_id,
        exchange_order_id=record.exchange_order_id,
        account_id=record.account_id,
        exchange=record.exchange,
        symbol=record.symbol,
        side=record.side,
        order_type=record.order_type,
        time_in_force=record.time_in_force,
        qty=record.qty,
        price=record.price,
        filled_qty=record.filled_qty,
        avg_fill_price=record.avg_fill_price,
        status=record.status,
        submitted_at=_shanghai_datetime(record.submitted_at),
        updated_at=_shanghai_datetime(record.updated_at),
        last_error_code=record.last_error_code,
        last_error_message=record.last_error_message,
    )


@dataclass(frozen=True, slots=True)
class OmsSubmission:
    """The persisted OMS objects produced by one signal-handling attempt."""

    signal: Signal
    plan: SignalOrderIntentPlan
    order_intent: OrderIntent
    order: Order


@dataclass(frozen=True, slots=True)
class CancelAllOrdersResult:
    """Summary of one operator-triggered cancel-all request."""

    requested_order_count: int
    cancelled_order_count: int
    skipped_order_count: int


class TraderOmsService:
    """Persist order intents before invoking any execution adapter."""

    def __init__(
        self,
        persistence: OmsPersistencePort,
        *,
        execution_gateway: ExecutionGateway | None = None,
        risk_gate: PreTradeRiskGate | None = None,
        control_store: TraderControlPlaneStore | None = None,
        observability: SignalArkObservability | None = None,
        paper_initial_cash: Decimal = DEFAULT_PAPER_INITIAL_CASH,
    ) -> None:
        if paper_initial_cash <= 0:
            raise ValueError("paper_initial_cash must be positive")
        self._persistence = persistence
        self._execution_gateway = execution_gateway or NoopExecutionGateway()
        self._risk_gate = risk_gate or PreTradeRiskGate()
        self._control_store = control_store
        self._observability = observability or SignalArkObservability(
            service="trader_oms",
            logger_name="signalark.trader.oms",
        )
        self._paper_initial_cash = paper_initial_cash

    async def submit_signal(
        self,
        *,
        signal: Signal,
        symbol_rule: AshareSymbolRule | None,
        decision_price: Decimal | None,
        market_context: MarketStateSnapshot | None,
        strategy_input_snapshot: dict[str, str | None] | None = None,
        strategy_signal_snapshot: dict[str, str] | None = None,
        strategy_reason_summary: str | None = None,
        current_position: Position | None = None,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal | None = None,
        control_state: RiskControlState | None = None,
        submission_guard: SubmissionLeaseGuard | None = None,
        received_at: datetime | None = None,
    ) -> OmsSubmission | None:
        """Persist Signal -> OrderIntent -> Order before execution handoff."""
        occurred_at = received_at or shanghai_now()
        resolved_control_state = control_state or RiskControlState.NORMAL
        if self._control_store is not None:
            control_snapshot = self._control_store.get_control_snapshot(signal.account_id)
            resolved_control_state = control_state or control_snapshot.control_state
            if submission_guard is not None:
                if submission_guard.account_id != signal.account_id:
                    self._persist_risk_rejection(
                        signal=signal,
                        risk_result=PreTradeRiskResult.reject(
                            reason_code="LEASE_ACCOUNT_MISMATCH",
                            reason_message=(
                                "submission_guard.account_id must match signal.account_id."
                            ),
                            rule_name="single_active_lease",
                            details={
                                "submission_guard_account_id": submission_guard.account_id,
                                "signal_account_id": signal.account_id,
                            },
                        ),
                        occurred_at=occurred_at,
                        current_position=current_position,
                        market_context=market_context,
                        order_type=order_type,
                        price=price,
                        decision_price=decision_price,
                        control_state=resolved_control_state,
                        plan=None,
                    )
                    return None
                lease_result = self._control_store.validate_submission_lease(
                    account_id=submission_guard.account_id,
                    instance_id=submission_guard.instance_id,
                    fencing_token=submission_guard.fencing_token,
                    now=occurred_at,
                )
                if not lease_result.accepted:
                    self._persist_risk_rejection(
                        signal=signal,
                        risk_result=PreTradeRiskResult.reject(
                            reason_code="LEASE_NOT_HELD",
                            reason_message=(
                                "The trader instance no longer holds the active submission lease."
                            ),
                            rule_name="single_active_lease",
                            details={
                                "instance_id": submission_guard.instance_id,
                                "fencing_token": submission_guard.fencing_token,
                                "lease_owner_instance_id": lease_result.snapshot.owner_instance_id,
                                "lease_expires_at": lease_result.snapshot.lease_expires_at,
                            },
                        ),
                        occurred_at=occurred_at,
                        current_position=current_position,
                        market_context=market_context,
                        order_type=order_type,
                        price=price,
                        decision_price=decision_price,
                        control_state=resolved_control_state,
                        plan=None,
                    )
                    return None
        persisted_signal = self._save_signal(signal)
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
                control_state=resolved_control_state,
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
                control_state=resolved_control_state,
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
                    "strategy_id": persisted_signal.strategy_id,
                    "signal_type": persisted_signal.signal_type.value,
                    "reason_summary": strategy_reason_summary or persisted_signal.reason_summary,
                    "strategy_input_snapshot": strategy_input_snapshot,
                    "strategy_signal_snapshot": strategy_signal_snapshot,
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
                    "control_state": resolved_control_state.value,
                },
            )
            return None

        order_intent = plan.to_order_intent(created_at=occurred_at)
        persisted_intent = self._save_order_intent(order_intent)

        order_id = build_order_id_for_intent(persisted_intent.id)
        if persisted_intent.status is OrderIntentStatus.SUBMITTED:
            existing_order = self._persistence.get_order(order_id)
            if existing_order is None:
                existing_order = self._save_order(
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
                "strategy_id": persisted_signal.strategy_id,
                "signal_type": persisted_signal.signal_type.value,
                "reason_summary": strategy_reason_summary or persisted_signal.reason_summary,
                "strategy_input_snapshot": strategy_input_snapshot,
                "strategy_signal_snapshot": strategy_signal_snapshot,
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
                "control_state": resolved_control_state.value,
                "fencing_token": submission_guard.fencing_token if submission_guard else None,
            },
        )

        order = create_order_from_intent(
            persisted_intent,
            order_id=order_id,
            submitted_at=occurred_at,
        )
        persisted_order = self._save_order(order)

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
                "fencing_token": submission_guard.fencing_token if submission_guard else None,
            },
        )

        try:
            execution_report = await self._execution_gateway.submit_order(
                persisted_order,
                persisted_intent,
            )
        except Exception as exc:
            self._activate_protection_mode(
                account_id=persisted_signal.account_id,
                trigger="EXECUTION_SUBMISSION_FAILED",
                details={
                    "order_id": persisted_order.id,
                    "order_intent_id": persisted_intent.id,
                    "error": str(exc),
                },
            )
            errored_order = persisted_order.model_copy(
                update={
                    "last_error_code": "SUBMIT_FAILED",
                    "last_error_message": str(exc),
                    "updated_at": occurred_at,
                }
            )
            self._save_order(errored_order)
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
                observed_severity="critical",
                notify=True,
                bypass_cooldown=True,
                observed_reason_code="SUBMIT_FAILED",
                observed_message="Execution submission failed after order persistence.",
            )
            raise

        submitted_intent = persisted_intent.model_copy(
            update={"status": OrderIntentStatus.SUBMITTED}
        )
        persisted_submitted_intent = self._save_order_intent(submitted_intent)

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
                "control_state": resolved_control_state.value,
                "fencing_token": submission_guard.fencing_token if submission_guard else None,
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

    async def cancel_all_orders(
        self,
        *,
        account_id: str,
        control_state: RiskControlState | None = None,
        received_at: datetime | None = None,
    ) -> CancelAllOrdersResult:
        """Cancel all active orders while preserving protective reduce-only orders."""
        occurred_at = received_at or shanghai_now()
        resolved_control_state = control_state or RiskControlState.NORMAL
        if self._control_store is not None and control_state is None:
            resolved_control_state = self._control_store.get_control_snapshot(
                account_id
            ).control_state

        active_orders = self._persistence.list_active_orders(account_id=account_id)
        cancelled_order_count = 0
        skipped_order_count = 0
        for order in active_orders:
            order_intent = self._persistence.get_order_intent(order.order_intent_id)
            if (
                resolved_control_state
                in {RiskControlState.KILL_SWITCH, RiskControlState.PROTECTION_MODE}
                and order_intent is not None
                and order_intent.reduce_only
            ):
                skipped_order_count += 1
                continue

            cancelled_order = await self.cancel_order(
                order_id=order.id,
                received_at=occurred_at,
            )
            if cancelled_order is None or cancelled_order.status is not OrderStatus.CANCELED:
                skipped_order_count += 1
                continue
            cancelled_order_count += 1

        return CancelAllOrdersResult(
            requested_order_count=len(active_orders),
            cancelled_order_count=cancelled_order_count,
            skipped_order_count=skipped_order_count,
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

    def recover_account_state(
        self,
        *,
        account_id: str,
        exchange: str,
        recovery_trader_run_id: UUID,
        effective_trade_date: date,
        event_limit: int = 100,
    ) -> RecoveryState:
        """Recover persisted paper state on startup and release T+1 sellable_qty when needed."""
        recovered_state = self._persistence.load_recovery_state(
            account_id=account_id,
            event_limit=event_limit,
        )
        occurred_at = shanghai_now()
        latest_balance_snapshots = self._seed_initial_balance_for_pristine_account(
            account_id=account_id,
            exchange=exchange,
            trader_run_id=recovery_trader_run_id,
            effective_trade_date=effective_trade_date,
            occurred_at=occurred_at,
            recovered_state=recovered_state,
        )
        released_positions = tuple(
            self._release_position_for_trade_date(
                position=position,
                effective_trade_date=effective_trade_date,
                occurred_at=occurred_at,
                trader_run_id=recovery_trader_run_id,
            )
            for position in recovered_state.open_positions
        )
        return RecoveryState(
            open_orders=recovered_state.open_orders,
            open_positions=tuple(
                position for position in released_positions if position is not None
            ),
            latest_balance_snapshots=latest_balance_snapshots,
            recent_event_logs=recovered_state.recent_event_logs,
        )

    def _seed_initial_balance_for_pristine_account(
        self,
        *,
        account_id: str,
        exchange: str,
        trader_run_id: UUID,
        effective_trade_date: date,
        occurred_at: datetime,
        recovered_state: RecoveryState,
    ) -> tuple[BalanceSnapshot, ...]:
        if recovered_state.latest_balance_snapshots:
            return recovered_state.latest_balance_snapshots
        if recovered_state.open_orders or recovered_state.open_positions:
            return recovered_state.latest_balance_snapshots
        if self._persistence.has_fill_history(account_id=account_id):
            return recovered_state.latest_balance_snapshots

        snapshot_time = datetime(
            effective_trade_date.year,
            effective_trade_date.month,
            effective_trade_date.day,
            tzinfo=SHANGHAI_TIMEZONE,
        )
        created_at = occurred_at if occurred_at >= snapshot_time else snapshot_time
        balance_snapshot = self._save_balance_snapshot(
            BalanceSnapshot(
                account_id=account_id,
                exchange=exchange,
                asset=PAPER_SETTLEMENT_ASSET,
                total=self._paper_initial_cash,
                available=self._paper_initial_cash,
                locked=Decimal("0"),
                snapshot_time=snapshot_time,
                created_at=created_at,
            )
        )
        self._save_event_log(
            EventLogEntry(
                event_type="portfolio.balance_initialized",
                source="trader_oms",
                trader_run_id=trader_run_id,
                account_id=account_id,
                exchange=exchange,
                related_object_type="balance_snapshot",
                related_object_id=balance_snapshot.id,
                event_time=occurred_at,
                ingest_time=occurred_at,
                payload_json={
                    "asset": balance_snapshot.asset,
                    "total": balance_snapshot.total,
                    "available": balance_snapshot.available,
                    "locked": balance_snapshot.locked,
                    "reason": "paper_initial_cash_bootstrap",
                },
                created_at=occurred_at,
            )
        )
        return (balance_snapshot,)

    def _apply_execution_report(
        self,
        *,
        report: ExecutionReport,
        initial_order: Order,
    ) -> Order:
        current_order = initial_order
        for order_update in report.order_updates:
            current_order = self._save_order(apply_order_update(current_order, order_update))
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

            persisted_fill = self._save_fill(fill_event.fill)
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
            persisted_position = self._save_position(portfolio_update.position)
            persisted_balance_snapshot = self._save_balance_snapshot(
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

        persisted_position = self._save_position(release.position)
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
        risk_repeat_count = self._observability.count_occurrence(
            series_key=f"risk_rejection|{signal.account_id}|{signal.symbol}|{risk_result.reason_code}",
            timestamp=occurred_at,
        )
        immediate_alert = risk_result.reason_code in {
            "LEASE_ACCOUNT_MISMATCH",
            "LEASE_NOT_HELD",
        }
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
                "risk_repeat_count": risk_repeat_count,
            },
            observed_severity="critical" if immediate_alert else "warning",
            notify=immediate_alert or risk_repeat_count >= 3,
            bypass_cooldown=immediate_alert,
            observed_reason_code=risk_result.reason_code,
            observed_message=risk_result.reason_message,
            extra_observability_details={"risk_repeat_count": risk_repeat_count},
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
        observed_severity: str | None = None,
        notify: bool = False,
        bypass_cooldown: bool = False,
        observed_reason_code: str | None = None,
        observed_message: str | None = None,
        extra_observability_details: dict[str, object] | None = None,
    ) -> None:
        entry = EventLogEntry(
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
        self._save_event_log(entry)
        signal_id, order_intent_id, order_id = self._related_ids_for_event(
            related_object_type=related_object_type,
            related_object_id=related_object_id,
            payload=payload,
        )
        risk_result = payload.get("risk_result")
        resolved_reason_code = observed_reason_code
        resolved_message = observed_message
        if isinstance(risk_result, PreTradeRiskResult):
            resolved_reason_code = resolved_reason_code or risk_result.reason_code
            resolved_message = resolved_message or risk_result.reason_message

        details = {
            "related_object_type": related_object_type,
            "related_object_id": related_object_id,
            "source": source,
            **payload,
        }
        if extra_observability_details:
            details.update(extra_observability_details)

        self._observability.emit(
            event_name=event_type,
            severity=observed_severity or _severity_for_event(event_type),
            message=resolved_message,
            notify=notify,
            bypass_cooldown=bypass_cooldown,
            timestamp=occurred_at,
            trader_run_id=trader_run_id,
            account_id=account_id,
            exchange=exchange,
            symbol=symbol,
            control_state=_extract_control_state(payload),
            reason_code=resolved_reason_code,
            signal_id=signal_id,
            order_intent_id=order_intent_id,
            order_id=order_id,
            fencing_token=_extract_fencing_token(payload),
            details=details,
        )

    def _save_signal(self, signal: Signal) -> Signal:
        return self._persist_write(
            write=lambda: self._persistence.save_signal(signal),
            event_name="db.signal_write_failed",
            message="Database write failed while persisting signal state.",
            trader_run_id=signal.trader_run_id,
            account_id=signal.account_id,
            exchange=signal.exchange,
            symbol=signal.symbol,
            signal_id=signal.id,
            reason_code="SIGNAL_WRITE_FAILED",
        )

    def _save_order_intent(self, order_intent: OrderIntent) -> OrderIntent:
        return self._persist_write(
            write=lambda: self._persistence.save_order_intent(order_intent),
            event_name="db.order_intent_write_failed",
            message="Database write failed while persisting order intent state.",
            trader_run_id=order_intent.trader_run_id,
            account_id=order_intent.account_id,
            exchange=order_intent.exchange,
            symbol=order_intent.symbol,
            signal_id=order_intent.signal_id,
            order_intent_id=order_intent.id,
            reason_code="ORDER_INTENT_WRITE_FAILED",
            enter_protection_mode=True,
            details={"status": order_intent.status},
        )

    def _save_order(self, order: Order) -> Order:
        return self._persist_write(
            write=lambda: self._persistence.save_order(order),
            event_name="db.order_write_failed",
            message="Database write failed while persisting order state.",
            trader_run_id=order.trader_run_id,
            account_id=order.account_id,
            exchange=order.exchange,
            symbol=order.symbol,
            order_intent_id=order.order_intent_id,
            order_id=order.id,
            reason_code="ORDER_WRITE_FAILED",
            enter_protection_mode=True,
            details={"status": order.status},
        )

    def _save_fill(self, fill: Fill) -> Fill:
        return self._persist_write(
            write=lambda: self._persistence.save_fill(fill),
            event_name="db.fill_write_failed",
            message="Database write failed while persisting fill state.",
            trader_run_id=fill.trader_run_id,
            account_id=fill.account_id,
            exchange=fill.exchange,
            symbol=fill.symbol,
            order_id=fill.order_id,
            reason_code="FILL_WRITE_FAILED",
            enter_protection_mode=True,
        )

    def _save_position(self, position: Position) -> Position:
        return self._persist_write(
            write=lambda: self._persistence.save_position(position),
            event_name="db.position_write_failed",
            message="Database write failed while persisting position state.",
            account_id=position.account_id,
            exchange=position.exchange,
            symbol=position.symbol,
            reason_code="POSITION_WRITE_FAILED",
            enter_protection_mode=True,
        )

    def _save_balance_snapshot(self, balance_snapshot: BalanceSnapshot) -> BalanceSnapshot:
        return self._persist_write(
            write=lambda: self._persistence.save_balance_snapshot(balance_snapshot),
            event_name="db.balance_snapshot_write_failed",
            message="Database write failed while persisting balance state.",
            account_id=balance_snapshot.account_id,
            exchange=balance_snapshot.exchange,
            reason_code="BALANCE_SNAPSHOT_WRITE_FAILED",
            enter_protection_mode=True,
            details={"asset": balance_snapshot.asset},
        )

    def _save_event_log(self, event_log: EventLogEntry) -> EventLogEntry:
        return self._persist_write(
            write=lambda: self._persistence.save_event_log(event_log),
            event_name="db.event_log_write_failed",
            message="Database write failed while persisting event-log state.",
            trader_run_id=event_log.trader_run_id,
            account_id=event_log.account_id,
            exchange=event_log.exchange,
            symbol=event_log.symbol,
            reason_code="EVENT_LOG_WRITE_FAILED",
            details={"event_type": event_log.event_type},
        )

    def _persist_write(
        self,
        *,
        write,
        event_name: str,
        message: str,
        reason_code: str,
        enter_protection_mode: bool = False,
        trader_run_id: UUID | None = None,
        account_id: str | None = None,
        exchange: str | None = None,
        symbol: str | None = None,
        signal_id: UUID | None = None,
        order_intent_id: UUID | None = None,
        order_id: UUID | None = None,
        details: dict[str, object] | None = None,
    ):
        try:
            return write()
        except Exception as exc:
            if enter_protection_mode and account_id is not None:
                self._activate_protection_mode(
                    account_id=account_id,
                    trigger=reason_code,
                    details={
                        "event_name": event_name,
                        "error": str(exc),
                    },
                )
            failure_details = dict(details or {})
            failure_details["error"] = str(exc)
            self._observability.emit(
                event_name=event_name,
                severity="critical",
                message=message,
                notify=True,
                bypass_cooldown=True,
                trader_run_id=trader_run_id,
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
                signal_id=signal_id,
                order_intent_id=order_intent_id,
                order_id=order_id,
                reason_code=reason_code,
                details=failure_details,
            )
            raise

    def _activate_protection_mode(
        self,
        *,
        account_id: str,
        trigger: str,
        details: dict[str, object],
    ) -> None:
        if self._control_store is None:
            return

        try:
            snapshot = self._control_store.set_protection_mode(
                account_id=account_id,
                active=True,
            )
        except Exception as exc:
            self._observability.emit(
                event_name="control.protection_mode_activation_failed",
                severity="critical",
                message="Automatic protection-mode activation failed after a critical OMS error.",
                notify=True,
                bypass_cooldown=True,
                account_id=account_id,
                reason_code="PROTECTION_MODE_ACTIVATION_FAILED",
                details={
                    "trigger": trigger,
                    "error": str(exc),
                    **details,
                },
            )
            return

        self._observability.emit(
            event_name="control.protection_mode_requested",
            severity="critical",
            message="OMS requested automatic protection mode after a critical failure.",
            notify=True,
            bypass_cooldown=True,
            account_id=account_id,
            control_state=snapshot.control_state.value,
            reason_code=trigger,
            details=details,
        )

    def _related_ids_for_event(
        self,
        *,
        related_object_type: str,
        related_object_id: UUID,
        payload: dict[str, object],
    ) -> tuple[UUID | None, UUID | None, UUID | None]:
        signal_id = payload.get("signal_id")
        order_intent_id = payload.get("order_intent_id")
        order_id = payload.get("order_id")
        if related_object_type == "signal":
            signal_id = related_object_id
        elif related_object_type == "order_intent":
            order_intent_id = related_object_id
        elif related_object_type == "order":
            order_id = related_object_id
        return signal_id, order_intent_id, order_id


def _severity_for_event(event_type: str) -> str:
    if event_type == "oms.risk_rejected":
        return "warning"
    if "failed" in event_type:
        return "error"
    return "info"


def _extract_control_state(payload: dict[str, object]) -> str | None:
    control_state = payload.get("control_state")
    if isinstance(control_state, str):
        return control_state
    return None


def _extract_fencing_token(payload: dict[str, object]) -> int | None:
    fencing_token = payload.get("fencing_token")
    if isinstance(fencing_token, int):
        return fencing_token
    return None
