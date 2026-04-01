"""Repository implementations for SignalArk Phase 2 persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from src.domain.execution import (
    Fill,
    Order,
    OrderIntent,
    OrderStatus,
    validate_order_status_transition,
)
from src.domain.portfolio import BalanceSnapshot, Position, PositionStatus
from src.domain.strategy import Signal
from src.infra.db.audit import EventLogEntry
from src.infra.db.models import (
    BalanceSnapshotRecord,
    EventLogRecord,
    FillRecord,
    OrderIntentRecord,
    OrderRecord,
    PositionRecord,
    SignalRecord,
)

ACTIVE_ORDER_STATUSES = (
    OrderStatus.NEW.value,
    OrderStatus.ACK.value,
    OrderStatus.PARTIALLY_FILLED.value,
)
SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True, slots=True)
class RecoveryState:
    """Minimal persisted state needed to bootstrap the trader after restart."""

    open_orders: tuple[Order, ...]
    open_positions: tuple[Position, ...]
    latest_balance_snapshots: tuple[BalanceSnapshot, ...]
    recent_event_logs: tuple[EventLogEntry, ...]


def _update_record_from_model(
    record: object,
    payload: dict[str, object],
    *,
    exclude: set[str],
) -> None:
    """Copy Pydantic model values into an ORM record."""
    for field_name, value in payload.items():
        if field_name in exclude:
            continue
        setattr(record, field_name, value)


def _shanghai_datetime(value: datetime) -> datetime:
    """Normalize database-loaded timestamps back to Asia/Shanghai-aware datetimes."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=SHANGHAI_TIMEZONE)
    return value.astimezone(SHANGHAI_TIMEZONE)


def _signal_from_record(record: SignalRecord) -> Signal:
    return Signal(
        id=record.id,
        strategy_id=record.strategy_id,
        trader_run_id=record.trader_run_id,
        account_id=record.account_id,
        exchange=record.exchange,
        symbol=record.symbol,
        timeframe=record.timeframe,
        signal_type=record.signal_type,
        target_position=record.target_position,
        confidence=record.confidence,
        reason_summary=record.reason_summary,
        status=record.status,
        event_time=_shanghai_datetime(record.event_time),
        created_at=_shanghai_datetime(record.created_at),
    )


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


def _fill_from_record(record: FillRecord) -> Fill:
    return Fill(
        id=record.id,
        order_id=record.order_id,
        trader_run_id=record.trader_run_id,
        exchange_fill_id=record.exchange_fill_id,
        account_id=record.account_id,
        exchange=record.exchange,
        symbol=record.symbol,
        side=record.side,
        qty=record.qty,
        price=record.price,
        fee=record.fee,
        fee_asset=record.fee_asset,
        liquidity_type=record.liquidity_type,
        fill_time=_shanghai_datetime(record.fill_time),
        created_at=_shanghai_datetime(record.created_at),
    )


def _position_from_record(record: PositionRecord) -> Position:
    return Position(
        id=record.id,
        account_id=record.account_id,
        exchange=record.exchange,
        symbol=record.symbol,
        side=record.side,
        qty=record.qty,
        sellable_qty=record.sellable_qty,
        avg_entry_price=record.avg_entry_price,
        mark_price=record.mark_price,
        unrealized_pnl=record.unrealized_pnl,
        realized_pnl=record.realized_pnl,
        status=record.status,
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


class SqlAlchemySignalRepository:
    """Signal persistence backed by SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, signal: Signal) -> Signal:
        existing = self.session.get(SignalRecord, signal.id)
        if existing is not None:
            return _signal_from_record(existing)

        record = SignalRecord(**signal.model_dump(mode="python"))
        self.session.add(record)
        self.session.flush()
        return _signal_from_record(record)

    def get(self, signal_id: UUID) -> Signal | None:
        record = self.session.get(SignalRecord, signal_id)
        return None if record is None else _signal_from_record(record)


class SqlAlchemyOrderIntentRepository:
    """Order intent persistence with idempotency-key protection."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, order_intent: OrderIntent) -> OrderIntent:
        existing = self.session.get(OrderIntentRecord, order_intent.id)
        if existing is None:
            existing = self.session.scalar(
                select(OrderIntentRecord).where(
                    OrderIntentRecord.idempotency_key == order_intent.idempotency_key
                )
            )

        payload = order_intent.model_dump(mode="python")
        if existing is None:
            record = OrderIntentRecord(**payload)
            self.session.add(record)
            self.session.flush()
            return _order_intent_from_record(record)

        if existing.id != order_intent.id:
            return _order_intent_from_record(existing)

        _update_record_from_model(existing, payload, exclude={"id"})
        self.session.flush()
        return _order_intent_from_record(existing)

    def get(self, order_intent_id: UUID) -> OrderIntent | None:
        record = self.session.get(OrderIntentRecord, order_intent_id)
        return None if record is None else _order_intent_from_record(record)


class SqlAlchemyOrderRepository:
    """Mutable order persistence keyed by exchange order ID when available."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, order: Order) -> Order:
        existing = None
        if order.exchange_order_id is not None:
            existing = self.session.scalar(
                select(OrderRecord).where(OrderRecord.exchange_order_id == order.exchange_order_id)
            )

        if existing is None:
            existing = self.session.get(OrderRecord, order.id)

        payload = order.model_dump(mode="python")
        if existing is None:
            record = OrderRecord(**payload)
            self.session.add(record)
            self.session.flush()
            return _order_from_record(record)

        validate_order_status_transition(OrderStatus(existing.status), order.status)
        _update_record_from_model(existing, payload, exclude={"id"})
        self.session.flush()
        return _order_from_record(existing)

    def get(self, order_id: UUID) -> Order | None:
        record = self.session.get(OrderRecord, order_id)
        return None if record is None else _order_from_record(record)


class SqlAlchemyFillRepository:
    """Immutable fill persistence with duplicate-write protection."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, fill: Fill) -> Fill:
        existing = None
        if fill.exchange_fill_id is not None:
            existing = self.session.scalar(
                select(FillRecord).where(FillRecord.exchange_fill_id == fill.exchange_fill_id)
            )

        if existing is None:
            existing = self.session.get(FillRecord, fill.id)

        if existing is not None:
            return _fill_from_record(existing)

        record = FillRecord(**fill.model_dump(mode="python"))
        self.session.add(record)
        self.session.flush()
        return _fill_from_record(record)

    def get(self, fill_id: UUID) -> Fill | None:
        record = self.session.get(FillRecord, fill_id)
        return None if record is None else _fill_from_record(record)


class SqlAlchemyPositionRepository:
    """Current-state position persistence keyed by account and symbol."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, position: Position) -> Position:
        existing = self.session.scalar(
            select(PositionRecord).where(
                PositionRecord.account_id == position.account_id,
                PositionRecord.exchange == position.exchange,
                PositionRecord.symbol == position.symbol,
            )
        )
        payload = position.model_dump(mode="python")

        if existing is None:
            record = PositionRecord(**payload)
            self.session.add(record)
            self.session.flush()
            return _position_from_record(record)

        _update_record_from_model(existing, payload, exclude={"id"})
        self.session.flush()
        return _position_from_record(existing)

    def get_by_symbol(
        self,
        *,
        account_id: str,
        exchange: str,
        symbol: str,
    ) -> Position | None:
        record = self.session.scalar(
            select(PositionRecord).where(
                PositionRecord.account_id == account_id,
                PositionRecord.exchange == exchange,
                PositionRecord.symbol == symbol,
            )
        )
        return None if record is None else _position_from_record(record)


class SqlAlchemyBalanceSnapshotRepository:
    """Balance snapshot persistence keyed by asset and snapshot timestamp."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, snapshot: BalanceSnapshot) -> BalanceSnapshot:
        existing = self.session.scalar(
            select(BalanceSnapshotRecord).where(
                BalanceSnapshotRecord.account_id == snapshot.account_id,
                BalanceSnapshotRecord.exchange == snapshot.exchange,
                BalanceSnapshotRecord.asset == snapshot.asset,
                BalanceSnapshotRecord.snapshot_time == snapshot.snapshot_time,
            )
        )
        if existing is not None:
            return _balance_snapshot_from_record(existing)

        record = BalanceSnapshotRecord(**snapshot.model_dump(mode="python"))
        self.session.add(record)
        self.session.flush()
        return _balance_snapshot_from_record(record)


class SqlAlchemyEventLogRepository:
    """Audit log persistence keyed by a stable event ID."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, event_log: EventLogEntry) -> EventLogEntry:
        existing = self.session.scalar(
            select(EventLogRecord).where(EventLogRecord.event_id == event_log.event_id)
        )
        if existing is not None:
            return _event_log_from_record(existing)

        record = EventLogRecord(**event_log.model_dump(mode="python"))
        self.session.add(record)
        self.session.flush()
        return _event_log_from_record(record)


class SqlAlchemyRecoveryRepository:
    """Read persisted state back into domain objects after restart."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def load_runtime_state(
        self,
        *,
        account_id: str,
        trader_run_id: UUID | None = None,
        event_limit: int = 100,
    ) -> RecoveryState:
        open_orders = tuple(
            _order_from_record(record)
            for record in self.session.scalars(
                select(OrderRecord)
                .where(
                    OrderRecord.account_id == account_id,
                    OrderRecord.status.in_(ACTIVE_ORDER_STATUSES),
                )
                .order_by(OrderRecord.updated_at.asc(), OrderRecord.id.asc())
            )
        )

        open_positions = tuple(
            _position_from_record(record)
            for record in self.session.scalars(
                select(PositionRecord)
                .where(
                    PositionRecord.account_id == account_id,
                    PositionRecord.status == PositionStatus.OPEN.value,
                )
                .order_by(PositionRecord.symbol.asc())
            )
        )

        latest_balance_time = (
            select(
                BalanceSnapshotRecord.asset.label("asset"),
                func.max(BalanceSnapshotRecord.snapshot_time).label("snapshot_time"),
            )
            .where(BalanceSnapshotRecord.account_id == account_id)
            .group_by(BalanceSnapshotRecord.asset)
            .subquery()
        )
        latest_balances = tuple(
            _balance_snapshot_from_record(record)
            for record in self.session.scalars(
                select(BalanceSnapshotRecord)
                .join(
                    latest_balance_time,
                    and_(
                        BalanceSnapshotRecord.asset == latest_balance_time.c.asset,
                        BalanceSnapshotRecord.snapshot_time == latest_balance_time.c.snapshot_time,
                    ),
                )
                .where(BalanceSnapshotRecord.account_id == account_id)
                .order_by(BalanceSnapshotRecord.asset.asc())
            )
        )

        event_query = select(EventLogRecord).order_by(
            desc(EventLogRecord.event_time),
            desc(EventLogRecord.id),
        )
        if trader_run_id is not None:
            event_query = event_query.where(EventLogRecord.trader_run_id == trader_run_id)
        else:
            event_query = event_query.where(EventLogRecord.account_id == account_id)

        recent_event_logs = tuple(
            _event_log_from_record(record)
            for record in self.session.scalars(event_query.limit(event_limit))
        )

        return RecoveryState(
            open_orders=open_orders,
            open_positions=open_positions,
            latest_balance_snapshots=latest_balances,
            recent_event_logs=recent_event_logs,
        )


@dataclass(slots=True)
class SqlAlchemyRepositories:
    """Small repository bundle to keep call sites straightforward."""

    signals: SqlAlchemySignalRepository
    order_intents: SqlAlchemyOrderIntentRepository
    orders: SqlAlchemyOrderRepository
    fills: SqlAlchemyFillRepository
    positions: SqlAlchemyPositionRepository
    balance_snapshots: SqlAlchemyBalanceSnapshotRepository
    event_logs: SqlAlchemyEventLogRepository
    recovery: SqlAlchemyRecoveryRepository

    @classmethod
    def from_session(cls, session: Session) -> SqlAlchemyRepositories:
        return cls(
            signals=SqlAlchemySignalRepository(session),
            order_intents=SqlAlchemyOrderIntentRepository(session),
            orders=SqlAlchemyOrderRepository(session),
            fills=SqlAlchemyFillRepository(session),
            positions=SqlAlchemyPositionRepository(session),
            balance_snapshots=SqlAlchemyBalanceSnapshotRepository(session),
            event_logs=SqlAlchemyEventLogRepository(session),
            recovery=SqlAlchemyRecoveryRepository(session),
        )
