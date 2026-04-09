"""Add persisted AI research settings table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260409_190000"
down_revision = "20260403_090000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "research_ai_settings" not in existing_tables:
        op.create_table(
            "research_ai_settings",
            sa.Column("account_id", sa.String(length=64), nullable=False),
            sa.Column("provider", sa.String(length=64), nullable=False),
            sa.Column("model", sa.String(length=128), nullable=False),
            sa.Column("base_url", sa.String(length=512), nullable=False),
            sa.Column("api_key", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("account_id", name=op.f("pk_research_ai_settings")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "research_ai_settings" in existing_tables:
        op.drop_table("research_ai_settings")
