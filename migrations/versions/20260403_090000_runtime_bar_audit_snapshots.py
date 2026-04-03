"""Add runtime bar audit snapshots to trader runtime status."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260403_090000"
down_revision = "20260402_000100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("trader_runtime_status")
    }

    if "last_seen_bars_json" not in existing_columns:
        op.add_column(
            "trader_runtime_status",
            sa.Column(
                "last_seen_bars_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )

    if "last_strategy_bars_json" not in existing_columns:
        op.add_column(
            "trader_runtime_status",
            sa.Column(
                "last_strategy_bars_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )

def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns("trader_runtime_status")
    }

    if "last_strategy_bars_json" in existing_columns:
        op.drop_column("trader_runtime_status", "last_strategy_bars_json")
    if "last_seen_bars_json" in existing_columns:
        op.drop_column("trader_runtime_status", "last_seen_bars_json")
