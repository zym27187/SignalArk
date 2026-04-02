from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from apps.api.control_plane import ApiControlPlaneService
from apps.api.main import create_app
from apps.trader.control_plane import TraderControlPlaneStore
from fastapi.testclient import TestClient
from src.config.settings import Settings
from src.infra.db import (
    EventLogEntry,
    SqlAlchemyRepositories,
    create_database_engine,
    create_session_factory,
)
from tests.support.migrations import upgrade_database

SHANGHAI = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 4, 1, 14, 0, tzinfo=SHANGHAI)
TRADER_RUN_ID = UUID("11111111-1111-4111-8111-111111111111")


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'phase9_api_diagnostics.sqlite3'}"


def test_api_replay_events_supports_time_range_trader_run_account_and_symbol_filters(
    tmp_path: Path,
) -> None:
    database_url = _database_url(tmp_path)
    settings = Settings(postgres_dsn=database_url)
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory, clock=lambda: NOW)

    with session_factory.begin() as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        repositories.event_logs.save(
            EventLogEntry(
                event_id=UUID("22222222-2222-4222-8222-222222222222"),
                event_type="reconciliation.drift_detected",
                source="trader_reconciliation",
                trader_run_id=TRADER_RUN_ID,
                account_id=settings.account_id,
                exchange=settings.exchange,
                symbol="600036.SH",
                related_object_type="account",
                event_time=NOW - timedelta(minutes=5),
                ingest_time=NOW - timedelta(minutes=5),
                created_at=NOW - timedelta(minutes=5),
                payload_json={"issue_count": 3},
            )
        )
        repositories.event_logs.save(
            EventLogEntry(
                event_id=UUID("33333333-3333-4333-8333-333333333333"),
                event_type="oms.order_persisted",
                source="trader_oms",
                trader_run_id=TRADER_RUN_ID,
                account_id=settings.account_id,
                exchange=settings.exchange,
                symbol="000001.SZ",
                related_object_type="order",
                event_time=NOW - timedelta(minutes=4),
                ingest_time=NOW - timedelta(minutes=4),
                created_at=NOW - timedelta(minutes=4),
                payload_json={"qty": "100"},
            )
        )

    service = ApiControlPlaneService(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
    )
    app = create_app(settings=settings, control_plane_service=service)

    with TestClient(app) as client:
        response = client.get(
            "/v1/diagnostics/replay-events",
            params={
                "start_time": (NOW - timedelta(minutes=6)).isoformat(),
                "end_time": (NOW - timedelta(minutes=4, seconds=30)).isoformat(),
                "trader_run_id": str(TRADER_RUN_ID),
                "account_id": settings.account_id,
                "symbol": "600036.SH",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["filters"]["account_id"] == settings.account_id
    assert payload["filters"]["symbol"] == "600036.SH"
    assert payload["events"][0]["event_type"] == "reconciliation.drift_detected"
    engine.dispose()
