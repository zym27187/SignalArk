"""Phase 2 core persistence tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260331_220500"
down_revision = None
branch_labels = None
depends_on = None

DECIMAL_28_10 = sa.Numeric(28, 10)
DECIMAL_12_6 = sa.Numeric(12, 6)


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.String(length=128), nullable=False),
        sa.Column("trader_run_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("signal_type", sa.String(length=16), nullable=False),
        sa.Column("target_position", DECIMAL_28_10, nullable=False),
        sa.Column("confidence", DECIMAL_12_6, nullable=True),
        sa.Column("reason_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signals")),
    )
    op.create_index(
        "ix_signals_strategy_id_symbol_event_time",
        "signals",
        ["strategy_id", "symbol", "event_time"],
        unique=False,
    )
    op.create_index(
        "ix_signals_trader_run_id_event_time",
        "signals",
        ["trader_run_id", "event_time"],
        unique=False,
    )

    op.create_table(
        "order_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("signal_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.String(length=128), nullable=False),
        sa.Column("trader_run_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("time_in_force", sa.String(length=8), nullable=False),
        sa.Column("qty", DECIMAL_28_10, nullable=False),
        sa.Column("price", DECIMAL_28_10, nullable=True),
        sa.Column("decision_price", DECIMAL_28_10, nullable=False),
        sa.Column("reduce_only", sa.Boolean(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("risk_decision", sa.String(length=16), nullable=False),
        sa.Column("risk_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["signals.id"],
            name=op.f("fk_order_intents_signal_id_signals"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_intents")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_order_intents_idempotency_key")),
    )
    op.create_index(
        "ix_order_intents_account_id_symbol_created_at",
        "order_intents",
        ["account_id", "symbol", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_order_intents_trader_run_id_created_at",
        "order_intents",
        ["trader_run_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_intent_id", sa.Uuid(), nullable=False),
        sa.Column("trader_run_id", sa.Uuid(), nullable=False),
        sa.Column("exchange_order_id", sa.String(length=128), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("time_in_force", sa.String(length=8), nullable=False),
        sa.Column("qty", DECIMAL_28_10, nullable=False),
        sa.Column("price", DECIMAL_28_10, nullable=True),
        sa.Column("filled_qty", DECIMAL_28_10, nullable=False),
        sa.Column("avg_fill_price", DECIMAL_28_10, nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_intent_id"],
            ["order_intents.id"],
            name=op.f("fk_orders_order_intent_id_order_intents"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("exchange_order_id", name=op.f("uq_orders_exchange_order_id")),
    )
    op.create_index(
        "ix_orders_account_id_symbol_status_updated_at",
        "orders",
        ["account_id", "symbol", "status", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_orders_trader_run_id_updated_at",
        "orders",
        ["trader_run_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "fills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("trader_run_id", sa.Uuid(), nullable=False),
        sa.Column("exchange_fill_id", sa.String(length=128), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("qty", DECIMAL_28_10, nullable=False),
        sa.Column("price", DECIMAL_28_10, nullable=False),
        sa.Column("fee", DECIMAL_28_10, nullable=False),
        sa.Column("fee_asset", sa.String(length=32), nullable=True),
        sa.Column("liquidity_type", sa.String(length=16), nullable=False),
        sa.Column("fill_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_fills_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fills")),
        sa.UniqueConstraint("exchange_fill_id", name=op.f("uq_fills_exchange_fill_id")),
    )
    op.create_index("ix_fills_order_id_fill_time", "fills", ["order_id", "fill_time"], unique=False)

    op.create_table(
        "positions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("qty", DECIMAL_28_10, nullable=False),
        sa.Column("avg_entry_price", DECIMAL_28_10, nullable=True),
        sa.Column("mark_price", DECIMAL_28_10, nullable=True),
        sa.Column("unrealized_pnl", DECIMAL_28_10, nullable=False),
        sa.Column("realized_pnl", DECIMAL_28_10, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_positions")),
        sa.UniqueConstraint(
            "account_id",
            "exchange",
            "symbol",
            name=op.f("uq_positions_account_id_exchange_symbol"),
        ),
    )
    op.create_index(
        "ix_positions_account_id_symbol",
        "positions",
        ["account_id", "symbol"],
        unique=False,
    )

    op.create_table(
        "balance_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("asset", sa.String(length=32), nullable=False),
        sa.Column("total", DECIMAL_28_10, nullable=False),
        sa.Column("available", DECIMAL_28_10, nullable=False),
        sa.Column("locked", DECIMAL_28_10, nullable=False),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_balance_snapshots")),
        sa.UniqueConstraint(
            "account_id",
            "exchange",
            "asset",
            "snapshot_time",
            name=op.f("uq_balance_snapshots_account_id_exchange_asset_snapshot_time"),
        ),
    )
    op.create_index(
        "ix_balance_snapshots_account_id_asset_snapshot_time",
        "balance_snapshots",
        ["account_id", "asset", "snapshot_time"],
        unique=False,
    )

    op.create_table(
        "event_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("trader_run_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=True),
        sa.Column("exchange", sa.String(length=32), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("related_object_type", sa.String(length=32), nullable=True),
        sa.Column("related_object_id", sa.Uuid(), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingest_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_logs")),
        sa.UniqueConstraint("event_id", name=op.f("uq_event_logs_event_id")),
    )
    op.create_index(
        "ix_event_logs_event_type_event_time",
        "event_logs",
        ["event_type", "event_time"],
        unique=False,
    )
    op.create_index(
        "ix_event_logs_trader_run_id_event_time",
        "event_logs",
        ["trader_run_id", "event_time"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_event_logs_trader_run_id_event_time", table_name="event_logs")
    op.drop_index("ix_event_logs_event_type_event_time", table_name="event_logs")
    op.drop_table("event_logs")

    op.drop_index(
        "ix_balance_snapshots_account_id_asset_snapshot_time",
        table_name="balance_snapshots",
    )
    op.drop_table("balance_snapshots")

    op.drop_index("ix_positions_account_id_symbol", table_name="positions")
    op.drop_table("positions")

    op.drop_index("ix_fills_order_id_fill_time", table_name="fills")
    op.drop_table("fills")

    op.drop_index("ix_orders_trader_run_id_updated_at", table_name="orders")
    op.drop_index("ix_orders_account_id_symbol_status_updated_at", table_name="orders")
    op.drop_table("orders")

    op.drop_index("ix_order_intents_trader_run_id_created_at", table_name="order_intents")
    op.drop_index("ix_order_intents_account_id_symbol_created_at", table_name="order_intents")
    op.drop_table("order_intents")

    op.drop_index("ix_signals_trader_run_id_event_time", table_name="signals")
    op.drop_index("ix_signals_strategy_id_symbol_event_time", table_name="signals")
    op.drop_table("signals")
