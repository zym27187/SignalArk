"""SQLAlchemy ORM models for the V1 persistence layer."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.infra.db.base import Base

DECIMAL_28_10 = Numeric(28, 10)
DECIMAL_12_6 = Numeric(12, 6)
UUID_COLUMN = Uuid(as_uuid=True)


class SignalRecord(Base):
    """Persisted strategy signals."""

    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_strategy_id_symbol_event_time", "strategy_id", "symbol", "event_time"),
        Index("ix_signals_trader_run_id_event_time", "trader_run_id", "event_time"),
    )

    id: Mapped[UUID] = mapped_column(UUID_COLUMN, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trader_run_id: Mapped[UUID] = mapped_column(UUID_COLUMN, nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_position: Mapped[Decimal] = mapped_column(DECIMAL_28_10, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(DECIMAL_12_6, nullable=True)
    reason_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW")
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OrderIntentRecord(Base):
    """Persisted post-risk order intents."""

    __tablename__ = "order_intents"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        Index(
            "ix_order_intents_account_id_symbol_created_at",
            "account_id",
            "symbol",
            "created_at",
        ),
        Index("ix_order_intents_trader_run_id_created_at", "trader_run_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(UUID_COLUMN, primary_key=True)
    signal_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN,
        ForeignKey("signals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    strategy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trader_run_id: Mapped[UUID] = mapped_column(UUID_COLUMN, nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    time_in_force: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[Decimal] = mapped_column(DECIMAL_28_10, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(DECIMAL_28_10, nullable=True)
    decision_price: Mapped[Decimal] = mapped_column(DECIMAL_28_10, nullable=False)
    reduce_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    market_context_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW")
    risk_decision: Mapped[str] = mapped_column(String(16), nullable=False, default="ALLOW")
    risk_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OrderRecord(Base):
    """Persisted OMS orders."""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("exchange_order_id"),
        Index(
            "ix_orders_account_id_symbol_status_updated_at",
            "account_id",
            "symbol",
            "status",
            "updated_at",
        ),
        Index("ix_orders_trader_run_id_updated_at", "trader_run_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(UUID_COLUMN, primary_key=True)
    order_intent_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN,
        ForeignKey("order_intents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trader_run_id: Mapped[UUID] = mapped_column(UUID_COLUMN, nullable=False)
    exchange_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    time_in_force: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[Decimal] = mapped_column(DECIMAL_28_10, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(DECIMAL_28_10, nullable=True)
    filled_qty: Mapped[Decimal] = mapped_column(DECIMAL_28_10, nullable=False, default=Decimal("0"))
    avg_fill_price: Mapped[Decimal | None] = mapped_column(DECIMAL_28_10, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FillRecord(Base):
    """Persisted execution fills."""

    __tablename__ = "fills"
    __table_args__ = (
        UniqueConstraint("exchange_fill_id"),
        Index("ix_fills_order_id_fill_time", "order_id", "fill_time"),
    )

    id: Mapped[UUID] = mapped_column(UUID_COLUMN, primary_key=True)
    order_id: Mapped[UUID] = mapped_column(
        UUID_COLUMN,
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trader_run_id: Mapped[UUID] = mapped_column(UUID_COLUMN, nullable=False)
    exchange_fill_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    qty: Mapped[Decimal] = mapped_column(DECIMAL_28_10, nullable=False)
    price: Mapped[Decimal] = mapped_column(DECIMAL_28_10, nullable=False)
    fee: Mapped[Decimal] = mapped_column(DECIMAL_28_10, nullable=False, default=Decimal("0"))
    fee_asset: Mapped[str | None] = mapped_column(String(32), nullable=True)
    liquidity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    fill_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PositionRecord(Base):
    """Persisted current per-symbol position state."""

    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("account_id", "exchange", "symbol"),
        Index("ix_positions_account_id_symbol", "account_id", "symbol"),
    )

    id: Mapped[UUID] = mapped_column(UUID_COLUMN, primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    qty: Mapped[Decimal] = mapped_column(DECIMAL_28_10, nullable=False, default=Decimal("0"))
    sellable_qty: Mapped[Decimal] = mapped_column(
        DECIMAL_28_10,
        nullable=False,
        default=Decimal("0"),
    )
    avg_entry_price: Mapped[Decimal | None] = mapped_column(DECIMAL_28_10, nullable=True)
    mark_price: Mapped[Decimal | None] = mapped_column(DECIMAL_28_10, nullable=True)
    unrealized_pnl: Mapped[Decimal] = mapped_column(DECIMAL_28_10, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(DECIMAL_28_10, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BalanceSnapshotRecord(Base):
    """Persisted balance snapshots."""

    __tablename__ = "balance_snapshots"
    __table_args__ = (
        UniqueConstraint("account_id", "exchange", "asset", "snapshot_time"),
        Index(
            "ix_balance_snapshots_account_id_asset_snapshot_time",
            "account_id",
            "asset",
            "snapshot_time",
        ),
    )

    id: Mapped[UUID] = mapped_column(UUID_COLUMN, primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    total: Mapped[Decimal] = mapped_column(DECIMAL_28_10, nullable=False)
    available: Mapped[Decimal] = mapped_column(DECIMAL_28_10, nullable=False)
    locked: Mapped[Decimal] = mapped_column(DECIMAL_28_10, nullable=False)
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EventLogRecord(Base):
    """Persisted audit trail for critical trading events."""

    __tablename__ = "event_logs"
    __table_args__ = (
        UniqueConstraint("event_id"),
        Index("ix_event_logs_event_type_event_time", "event_type", "event_time"),
        Index("ix_event_logs_trader_run_id_event_time", "trader_run_id", "event_time"),
    )

    id: Mapped[UUID] = mapped_column(UUID_COLUMN, primary_key=True)
    event_id: Mapped[UUID] = mapped_column(UUID_COLUMN, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    trader_run_id: Mapped[UUID] = mapped_column(UUID_COLUMN, nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(32), nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    related_object_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    related_object_id: Mapped[UUID | None] = mapped_column(UUID_COLUMN, nullable=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingest_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
