from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from src.infra.db import create_database_engine

ROOT_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = ROOT_DIR / "migrations" / "alembic.ini"
EXPECTED_PHASE2_TABLES = {
    "signals",
    "order_intents",
    "orders",
    "fills",
    "positions",
    "balance_snapshots",
    "event_logs",
    "trader_controls",
    "trader_account_leases",
    "trader_runtime_status",
    "alembic_version",
}
HEAD_REVISION = "20260403_090000"


def _sqlite_database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path}"


def test_alembic_upgrade_smoke_uses_explicit_sqlalchemy_url(tmp_path: Path, monkeypatch) -> None:
    target_database_url = _sqlite_database_url(tmp_path / "alembic_target.sqlite3")
    fallback_database_url = _sqlite_database_url(tmp_path / "settings_fallback.sqlite3")
    monkeypatch.setenv("SIGNALARK_POSTGRES_DSN", fallback_database_url)

    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("sqlalchemy.url", target_database_url)
    command.upgrade(config, "head")

    target_engine = create_database_engine(target_database_url)
    fallback_engine = create_database_engine(fallback_database_url)
    try:
        assert EXPECTED_PHASE2_TABLES.issubset(set(inspect(target_engine).get_table_names()))
        with target_engine.connect() as connection:
            applied_revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        assert applied_revision == HEAD_REVISION
        assert inspect(fallback_engine).get_table_names() == []
    finally:
        target_engine.dispose()
        fallback_engine.dispose()
