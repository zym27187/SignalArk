"""Add persisted runtime symbol request table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260411_110000"
down_revision = "20260409_190000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "runtime_symbol_requests" not in existing_tables:
        op.create_table(
            "runtime_symbol_requests",
            sa.Column("account_id", sa.String(length=64), nullable=False),
            sa.Column("symbol", sa.String(length=32), nullable=False),
            sa.Column("requested_action", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("apply_mode", sa.String(length=32), nullable=False),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint(
                "account_id",
                "symbol",
                name=op.f("pk_runtime_symbol_requests"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "runtime_symbol_requests" in existing_tables:
        op.drop_table("runtime_symbol_requests")
