"""Alembic environment for SignalArk Phase 2 migrations."""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _get_target_metadata():
    import src.infra.db.models  # noqa: F401
    from src.infra.db.base import Base

    return Base.metadata


target_metadata = _get_target_metadata()


def _configured_database_url() -> str | None:
    """Return an explicitly configured Alembic URL when one was provided."""
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url is None:
        return None
    normalized_url = configured_url.strip()
    return normalized_url or None


def _resolve_database_url() -> str:
    """Use an explicit Alembic URL first, then fall back to the project runtime DSN."""
    configured_url = _configured_database_url()
    if configured_url is not None:
        return configured_url

    from src.config import load_settings

    return load_settings().postgres_dsn


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    url = _resolve_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""
    config.set_main_option("sqlalchemy.url", _resolve_database_url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
