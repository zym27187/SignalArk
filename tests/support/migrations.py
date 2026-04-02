from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = ROOT_DIR / "migrations" / "alembic.ini"


def upgrade_database(database_url: str) -> None:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def sqlite_database_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path}"
