"""Add control-plane persistence tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260402_000100"
down_revision = "20260331_220500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "trader_controls" not in existing_tables:
        op.create_table(
            "trader_controls",
            sa.Column("account_id", sa.String(length=64), nullable=False),
            sa.Column("strategy_enabled", sa.Boolean(), nullable=False),
            sa.Column("kill_switch_active", sa.Boolean(), nullable=False),
            sa.Column("protection_mode_active", sa.Boolean(), nullable=False),
            sa.Column("cancel_all_token", sa.Integer(), nullable=False),
            sa.Column("last_cancel_all_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("account_id", name=op.f("pk_trader_controls")),
        )

    if "trader_account_leases" not in existing_tables:
        op.create_table(
            "trader_account_leases",
            sa.Column("account_id", sa.String(length=64), nullable=False),
            sa.Column("owner_instance_id", sa.String(length=255), nullable=True),
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("fencing_token", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("account_id", name=op.f("pk_trader_account_leases")),
        )

    if "trader_runtime_status" not in existing_tables:
        op.create_table(
            "trader_runtime_status",
            sa.Column("account_id", sa.String(length=64), nullable=False),
            sa.Column("trader_run_id", sa.String(length=64), nullable=False),
            sa.Column("instance_id", sa.String(length=255), nullable=False),
            sa.Column("lifecycle_status", sa.String(length=32), nullable=False),
            sa.Column("health_status", sa.String(length=32), nullable=False),
            sa.Column("readiness_status", sa.String(length=32), nullable=False),
            sa.Column("control_state", sa.String(length=32), nullable=False),
            sa.Column("strategy_enabled", sa.Boolean(), nullable=False),
            sa.Column("kill_switch_active", sa.Boolean(), nullable=False),
            sa.Column("protection_mode_active", sa.Boolean(), nullable=False),
            sa.Column("market_data_fresh", sa.Boolean(), nullable=False),
            sa.Column("latest_final_bar_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("current_trading_phase", sa.String(length=64), nullable=True),
            sa.Column("fencing_token", sa.Integer(), nullable=True),
            sa.Column("last_status_message", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("account_id", name=op.f("pk_trader_runtime_status")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "trader_runtime_status" in existing_tables:
        op.drop_table("trader_runtime_status")
    if "trader_account_leases" in existing_tables:
        op.drop_table("trader_account_leases")
    if "trader_controls" in existing_tables:
        op.drop_table("trader_controls")
