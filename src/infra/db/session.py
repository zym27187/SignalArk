"""Database engine and session helpers for SignalArk."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import Settings, get_settings


def normalize_database_url(database_url: str) -> str:
    """Normalize supported SQLAlchemy URLs for runtime and tests."""
    normalized = database_url.strip()
    if normalized.startswith("postgresql://"):
        return normalized.replace("postgresql://", "postgresql+psycopg://", 1)
    return normalized


def create_database_engine(
    database_url: str | None = None,
    *,
    settings: Settings | None = None,
    echo: bool = False,
) -> Engine:
    """Create a SQLAlchemy engine using the configured project DSN by default."""
    if database_url is not None:
        resolved_url = normalize_database_url(database_url)
    else:
        resolved_settings = settings or get_settings()
        resolved_url = normalize_database_url(resolved_settings.postgres_dsn)

    connect_args: dict[str, object] = {}
    if resolved_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    return create_engine(
        resolved_url,
        echo=echo,
        future=True,
        pool_pre_ping=not resolved_url.startswith("sqlite"),
        connect_args=connect_args,
    )


def create_session_factory(
    engine: Engine,
    *,
    expire_on_commit: bool = False,
) -> sessionmaker[Session]:
    """Create a reusable SQLAlchemy session factory."""
    return sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=expire_on_commit,
    )


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Wrap a database session in a commit-or-rollback transaction boundary."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
