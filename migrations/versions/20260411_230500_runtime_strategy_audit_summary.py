"""Add persisted runtime strategy audit summary fields."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260411_230500"
down_revision = "20260411_110000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("trader_runtime_status")
    }

    if "last_strategy_id" not in existing_columns:
        op.add_column(
            "trader_runtime_status",
            sa.Column("last_strategy_id", sa.String(length=128), nullable=True),
        )

    if "last_strategy_decision_at" not in existing_columns:
        op.add_column(
            "trader_runtime_status",
            sa.Column("last_strategy_decision_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "last_strategy_audit_json" not in existing_columns:
        op.add_column(
            "trader_runtime_status",
            sa.Column("last_strategy_audit_json", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("trader_runtime_status")
    }

    if "last_strategy_audit_json" in existing_columns:
        op.drop_column("trader_runtime_status", "last_strategy_audit_json")
    if "last_strategy_decision_at" in existing_columns:
        op.drop_column("trader_runtime_status", "last_strategy_decision_at")
    if "last_strategy_id" in existing_columns:
        op.drop_column("trader_runtime_status", "last_strategy_id")
