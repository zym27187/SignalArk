"""Startup recovery, scheduled paper reconciliation, and replay helpers."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import sessionmaker
from src.config.settings import PaperCostModel
from src.domain.execution import (
    Fill,
    LiquidityType,
    Order,
    OrderIntent,
    OrderIntentStatus,
    OrderSide,
    OrderStatus,
    OrderType,
    RiskDecision,
    TimeInForce,
)
from src.domain.portfolio import BalanceSnapshot, Position, PositionSide, PositionStatus
from src.domain.reconciliation import (
    PaperReconciliationFacts,
    PaperReconciliationResult,
    ReplayEventFilters,
    reconcile_paper_state,
)
from src.infra.db import EventLogEntry, session_scope
from src.infra.db.models import (
    BalanceSnapshotRecord,
    EventLogRecord,
    FillRecord,
    OrderIntentRecord,
    OrderRecord,
    PositionRecord,
)
from src.infra.observability import SignalArkObservability
from src.shared.types import SHANGHAI_TIMEZONE, shanghai_now

from apps.trader.control_plane import TraderControlPlaneStore
from apps.trader.oms import TraderOmsService

if TYPE_CHECKING:
    from apps.trader.control_plane import TraderControlRuntime
    from apps.trader.runtime import TraderRuntimeState


class SessionFactoryBackedReconciliationStore:
    """Load persisted paper facts and replayable audit events from SQLAlchemy."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def load_paper_facts(
        self,
        *,
        account_id: str,
        exchange: str,
        effective_trade_date,
        trigger: str,
    ) -> PaperReconciliationFacts:
        with session_scope(self._session_factory) as session:
            order_intents = tuple(
                _order_intent_from_record(record)
                for record in session.scalars(
                    select(OrderIntentRecord)
                    .where(OrderIntentRecord.account_id == account_id)
                    .order_by(OrderIntentRecord.created_at.asc(), OrderIntentRecord.id.asc())
                )
            )
            orders = tuple(
                _order_from_record(record)
                for record in session.scalars(
                    select(OrderRecord)
                    .where(OrderRecord.account_id == account_id)
                    .order_by(OrderRecord.updated_at.asc(), OrderRecord.id.asc())
                )
            )
            fills = tuple(
                _fill_from_record(record)
                for record in session.scalars(
                    select(FillRecord)
                    .where(FillRecord.account_id == account_id)
                    .order_by(FillRecord.fill_time.asc(), FillRecord.id.asc())
                )
            )
            positions = tuple(
                _position_from_record(record)
                for record in session.scalars(
                    select(PositionRecord)
                    .where(PositionRecord.account_id == account_id)
                    .order_by(PositionRecord.symbol.asc(), PositionRecord.id.asc())
                )
            )
            balance_snapshots = tuple(
                _balance_snapshot_from_record(record)
                for record in session.scalars(
                    select(BalanceSnapshotRecord)
                    .where(BalanceSnapshotRecord.account_id == account_id)
                    .order_by(
                        BalanceSnapshotRecord.snapshot_time.asc(),
                        BalanceSnapshotRecord.id.asc(),
                    )
                )
            )

        return PaperReconciliationFacts(
            account_id=account_id,
            exchange=exchange,
            effective_trade_date=effective_trade_date,
            trigger=trigger,
            order_intents=order_intents,
            orders=orders,
            fills=fills,
            positions=positions,
            balance_snapshots=balance_snapshots,
        )

    def replay_events(self, filters: ReplayEventFilters) -> tuple[EventLogEntry, ...]:
        with session_scope(self._session_factory) as session:
            query = select(EventLogRecord).order_by(
                desc(EventLogRecord.event_time),
                desc(EventLogRecord.id),
            )
            if filters.start_time is not None:
                query = query.where(EventLogRecord.event_time >= filters.start_time)
            if filters.end_time is not None:
                query = query.where(EventLogRecord.event_time <= filters.end_time)
            if filters.trader_run_id is not None:
                query = query.where(EventLogRecord.trader_run_id == filters.trader_run_id)
            if filters.account_id is not None:
                query = query.where(EventLogRecord.account_id == filters.account_id)
            if filters.symbol is not None:
                query = query.where(EventLogRecord.symbol == filters.symbol)
            return tuple(
                _event_log_from_record(record)
                for record in session.scalars(query.limit(filters.limit))
            )

    def save_event_log(self, event_log: EventLogEntry) -> EventLogEntry:
        with session_scope(self._session_factory) as session:
            existing = session.scalar(
                select(EventLogRecord).where(EventLogRecord.event_id == event_log.event_id)
            )
            if existing is not None:
                return _event_log_from_record(existing)

            record = EventLogRecord(**event_log.model_dump(mode="python"))
            session.add(record)
            session.flush()
            return _event_log_from_record(record)


class TraderReconciliationRuntime:
    """Own startup recovery and periodic paper reconciliation for one trader."""

    def __init__(
        self,
        store: SessionFactoryBackedReconciliationStore,
        *,
        oms_service: TraderOmsService,
        control_store: TraderControlPlaneStore,
        account_id: str,
        exchange: str,
        cost_model: PaperCostModel,
        control_runtime: TraderControlRuntime | None = None,
        observability: SignalArkObservability | None = None,
        reconciliation_interval_seconds: int = 60,
        clock=shanghai_now,
        enable_background_task: bool = True,
    ) -> None:
        self._store = store
        self._oms_service = oms_service
        self._control_store = control_store
        self._account_id = account_id
        self._exchange = exchange
        self._cost_model = cost_model
        self._control_runtime = control_runtime
        self._observability = observability or SignalArkObservability(
            service="trader",
            logger_name="signalark.trader.reconciliation",
            clock=clock,
        )
        self._reconciliation_interval_seconds = reconciliation_interval_seconds
        self._clock = clock
        self._enable_background_task = enable_background_task
        self._runtime_state: TraderRuntimeState | None = None
        self._last_result: PaperReconciliationResult | None = None
        self._stop_event = asyncio.Event()
        self._background_task: asyncio.Task[None] | None = None

    @property
    def last_result(self) -> PaperReconciliationResult | None:
        return self._last_result

    async def start(self, runtime_state: TraderRuntimeState) -> None:
        self._runtime_state = runtime_state
        recovered_state = None
        checked_at = self._clock()
        try:
            recovered_state = self._oms_service.recover_account_state(
                account_id=self._account_id,
                exchange=self._exchange,
                recovery_trader_run_id=UUID(runtime_state.trader_run_id),
                effective_trade_date=checked_at.date(),
                event_limit=20,
            )
        except Exception as exc:
            await self._handle_failure(
                trigger="startup_recovery",
                checked_at=checked_at,
                exc=exc,
            )
        else:
            self._persist_event(
                event_type="reconciliation.startup_recovery_completed",
                checked_at=checked_at,
                message="Startup recovery loaded persisted paper state.",
                payload={
                    "open_order_count": len(recovered_state.open_orders),
                    "open_position_count": len(recovered_state.open_positions),
                    "balance_snapshot_count": len(recovered_state.latest_balance_snapshots),
                    "recent_event_count": len(recovered_state.recent_event_logs),
                },
            )
            self._emit(
                event_name="reconciliation.startup_recovery_completed",
                severity="info",
                message="Startup recovery loaded persisted paper state.",
                reason_code="STARTUP_RECOVERY_COMPLETED",
                details={
                    "open_order_count": len(recovered_state.open_orders),
                    "open_position_count": len(recovered_state.open_positions),
                    "balance_snapshot_count": len(recovered_state.latest_balance_snapshots),
                },
            )

        await self.run_once(trigger="startup")
        if self._enable_background_task:
            self._background_task = asyncio.create_task(
                self._loop(),
                name=f"trader-reconciliation:{self._account_id}",
            )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._background_task is not None:
            self._background_task.cancel()
            await asyncio.gather(self._background_task, return_exceptions=True)
            self._background_task = None

    async def run_once(self, *, trigger: str) -> PaperReconciliationResult | None:
        checked_at = self._clock()
        try:
            facts = self._store.load_paper_facts(
                account_id=self._account_id,
                exchange=self._exchange,
                effective_trade_date=checked_at.date(),
                trigger=trigger,
            )
            result = reconcile_paper_state(
                facts=facts,
                cost_model=self._cost_model,
                checked_at=checked_at,
            )
        except Exception as exc:
            await self._handle_failure(trigger=trigger, checked_at=checked_at, exc=exc)
            return None

        self._last_result = result
        if result.has_drift:
            await self._handle_drift(result)
        else:
            self._emit(
                event_name="reconciliation.completed",
                severity="info",
                message="Paper reconciliation completed without drift.",
                reason_code="RECONCILIATION_OK",
                details={"summary": result.summary},
            )
        return result

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._reconciliation_interval_seconds,
                )
                return
            except TimeoutError:
                await self.run_once(trigger="scheduled")

    async def _handle_drift(self, result: PaperReconciliationResult) -> None:
        sampled_issues = result.issues[:20]
        self._persist_event(
            event_type="reconciliation.drift_detected",
            checked_at=result.checked_at,
            message="Paper reconciliation detected persisted-state drift.",
            payload={
                "trigger": result.trigger,
                "summary": result.summary,
                "issue_count": len(result.issues),
                "issues": sampled_issues,
            },
        )
        self._emit(
            event_name="reconciliation.drift_detected",
            severity="critical",
            message="Paper reconciliation detected persisted-state drift.",
            notify=True,
            bypass_cooldown=True,
            reason_code="RECONCILIATION_DRIFT",
            details={
                "trigger": result.trigger,
                "issue_count": len(result.issues),
                "issue_codes": [issue.code for issue in sampled_issues],
                "summary": result.summary,
            },
        )
        await self._engage_protection_mode(
            checked_at=result.checked_at,
            reason_code="RECONCILIATION_DRIFT",
            payload={
                "trigger": result.trigger,
                "issue_count": len(result.issues),
                "issues": sampled_issues,
                "summary": result.summary,
            },
        )

    async def _handle_failure(
        self,
        *,
        trigger: str,
        checked_at: datetime,
        exc: Exception,
    ) -> None:
        self._persist_event(
            event_type="reconciliation.failed",
            checked_at=checked_at,
            message="Paper reconciliation failed before drift evaluation completed.",
            payload={"trigger": trigger, "error": str(exc)},
        )
        self._emit(
            event_name="reconciliation.failed",
            severity="critical",
            message="Paper reconciliation failed before drift evaluation completed.",
            notify=True,
            bypass_cooldown=True,
            reason_code="RECONCILIATION_FAILED",
            details={"trigger": trigger, "error": str(exc)},
        )
        await self._engage_protection_mode(
            checked_at=checked_at,
            reason_code="RECONCILIATION_FAILED",
            payload={"trigger": trigger, "error": str(exc)},
        )

    async def _engage_protection_mode(
        self,
        *,
        checked_at: datetime,
        reason_code: str,
        payload: dict[str, object],
    ) -> None:
        snapshot = self._control_store.set_protection_mode(
            account_id=self._account_id,
            active=True,
        )
        cancel_result = await self._oms_service.cancel_all_orders(
            account_id=self._account_id,
            control_state=snapshot.control_state,
            received_at=checked_at,
        )
        self._persist_event(
            event_type="reconciliation.protection_mode_engaged",
            checked_at=checked_at,
            message="Protection mode engaged after reconciliation risk was detected.",
            payload={
                **payload,
                "control_state": snapshot.control_state.value,
                "cancelled_order_count": cancel_result.cancelled_order_count,
                "skipped_order_count": cancel_result.skipped_order_count,
                "requested_order_count": cancel_result.requested_order_count,
            },
        )
        self._emit(
            event_name="reconciliation.protection_mode_engaged",
            severity="critical",
            message="Protection mode engaged after reconciliation risk was detected.",
            notify=True,
            bypass_cooldown=True,
            reason_code=reason_code,
            details={
                **payload,
                "control_state": snapshot.control_state.value,
                "cancelled_order_count": cancel_result.cancelled_order_count,
                "skipped_order_count": cancel_result.skipped_order_count,
                "requested_order_count": cancel_result.requested_order_count,
            },
        )
        if self._control_runtime is not None:
            await self._control_runtime.refresh(
                reason="reconciliation_protection_mode",
                force_heartbeat=False,
            )

    def _persist_event(
        self,
        *,
        event_type: str,
        checked_at: datetime,
        message: str,
        payload: dict[str, object],
    ) -> None:
        runtime_state = self._runtime_state
        if runtime_state is None:
            return
        event_log = EventLogEntry(
            event_type=event_type,
            source="trader_reconciliation",
            trader_run_id=UUID(runtime_state.trader_run_id),
            account_id=self._account_id,
            exchange=self._exchange,
            related_object_type="account",
            event_time=checked_at,
            ingest_time=checked_at,
            created_at=checked_at,
            payload_json={"message": message, **payload},
        )
        try:
            self._store.save_event_log(event_log)
        except Exception as exc:
            self._emit(
                event_name="reconciliation.event_log_write_failed",
                severity="critical",
                message="Reconciliation failed to persist a diagnostic event log.",
                notify=True,
                bypass_cooldown=True,
                reason_code="RECONCILIATION_EVENT_LOG_WRITE_FAILED",
                details={"event_type": event_type, "error": str(exc)},
            )

    def _emit(
        self,
        *,
        event_name: str,
        severity: str,
        message: str,
        notify: bool = False,
        bypass_cooldown: bool = False,
        reason_code: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        runtime_state = self._runtime_state
        self._observability.emit(
            event_name=event_name,
            severity=severity,
            message=message,
            notify=notify,
            bypass_cooldown=bypass_cooldown,
            trader_run_id=runtime_state.trader_run_id if runtime_state is not None else None,
            instance_id=runtime_state.instance_id if runtime_state is not None else None,
            account_id=self._account_id,
            exchange=self._exchange,
            control_state=(
                runtime_state.control_state.value if runtime_state is not None else None
            ),
            reason_code=reason_code,
            details=details,
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
        side=OrderSide(record.side),
        order_type=OrderType(record.order_type),
        time_in_force=TimeInForce(record.time_in_force),
        qty=record.qty,
        price=record.price,
        decision_price=record.decision_price,
        reduce_only=record.reduce_only,
        market_context_json=record.market_context_json,
        idempotency_key=record.idempotency_key,
        status=OrderIntentStatus(record.status),
        risk_decision=RiskDecision(record.risk_decision),
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
        side=OrderSide(record.side),
        order_type=OrderType(record.order_type),
        time_in_force=TimeInForce(record.time_in_force),
        qty=record.qty,
        price=record.price,
        filled_qty=record.filled_qty,
        avg_fill_price=record.avg_fill_price,
        status=OrderStatus(record.status),
        submitted_at=_shanghai_datetime(record.submitted_at),
        updated_at=_shanghai_datetime(record.updated_at),
        last_error_code=record.last_error_code,
        last_error_message=record.last_error_message,
    )


def _fill_from_record(record: FillRecord) -> Fill:
    return Fill(
        id=record.id,
        order_id=record.order_id,
        trader_run_id=record.trader_run_id,
        exchange_fill_id=record.exchange_fill_id,
        account_id=record.account_id,
        exchange=record.exchange,
        symbol=record.symbol,
        side=OrderSide(record.side),
        qty=record.qty,
        price=record.price,
        fee=record.fee,
        fee_asset=record.fee_asset,
        liquidity_type=LiquidityType(record.liquidity_type),
        fill_time=_shanghai_datetime(record.fill_time),
        created_at=_shanghai_datetime(record.created_at),
    )


def _position_from_record(record: PositionRecord) -> Position:
    return Position(
        id=record.id,
        account_id=record.account_id,
        exchange=record.exchange,
        symbol=record.symbol,
        side=PositionSide(record.side),
        qty=record.qty,
        sellable_qty=record.sellable_qty,
        avg_entry_price=record.avg_entry_price,
        mark_price=record.mark_price,
        unrealized_pnl=record.unrealized_pnl,
        realized_pnl=record.realized_pnl,
        status=PositionStatus(record.status),
        updated_at=_shanghai_datetime(record.updated_at),
    )


def _balance_snapshot_from_record(record: BalanceSnapshotRecord) -> BalanceSnapshot:
    return BalanceSnapshot(
        id=record.id,
        account_id=record.account_id,
        exchange=record.exchange,
        asset=record.asset,
        total=record.total,
        available=record.available,
        locked=record.locked,
        snapshot_time=_shanghai_datetime(record.snapshot_time),
        created_at=_shanghai_datetime(record.created_at),
    )


def _event_log_from_record(record: EventLogRecord) -> EventLogEntry:
    return EventLogEntry(
        id=record.id,
        event_id=record.event_id,
        event_type=record.event_type,
        source=record.source,
        trader_run_id=record.trader_run_id,
        account_id=record.account_id,
        exchange=record.exchange,
        symbol=record.symbol,
        related_object_type=record.related_object_type,
        related_object_id=record.related_object_id,
        event_time=_shanghai_datetime(record.event_time),
        ingest_time=_shanghai_datetime(record.ingest_time),
        payload_json=record.payload_json,
        created_at=_shanghai_datetime(record.created_at),
    )
