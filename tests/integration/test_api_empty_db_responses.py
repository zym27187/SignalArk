from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from apps.api.control_plane import ApiControlPlaneService
from apps.trader.control_plane import TraderControlPlaneStore
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from src.config.settings import Settings
from src.domain.market import NormalizedBar
from src.infra.db import create_database_engine, create_session_factory

SHANGHAI = ZoneInfo("Asia/Shanghai")


class FakeHistoricalBarGateway:
    async def fetch_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_bars: int | None = None,
    ) -> list[NormalizedBar]:
        del symbol, timeframe, start_time, end_time, max_bars
        bar_end_time = datetime(2026, 4, 2, 9, 45, tzinfo=SHANGHAI)
        return [
            NormalizedBar(
                exchange="cn_equity",
                symbol="600036.SH",
                timeframe="15m",
                bar_start_time=bar_end_time - timedelta(minutes=15),
                bar_end_time=bar_end_time,
                ingest_time=bar_end_time + timedelta(minutes=1),
                open="39.40",
                high="39.52",
                low="39.35",
                close="39.48",
                volume="118000",
                quote_volume="4658640",
                closed=True,
                final=True,
                source_kind="historical",
            )
        ]

    async def aclose(self) -> None:
        return None


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'empty_api.sqlite3'}"


def test_api_read_endpoints_return_empty_payloads_before_core_tables_exist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv("SIGNALARK_POSTGRES_DSN", database_url)
    from src.config import get_settings

    get_settings.cache_clear()
    from apps.api.main import create_app

    settings = Settings(postgres_dsn=database_url)
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory)
    service = ApiControlPlaneService(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        market_gateway_factory=FakeHistoricalBarGateway,
    )
    app = create_app(settings=settings, control_plane_service=service)

    try:
        with TestClient(app) as client:
            ready = client.get("/health/ready")
            status = client.get("/v1/status")
            positions = client.get("/v1/positions")
            active_orders = client.get("/v1/orders/active")
            order_history = client.get("/v1/orders/history", params={"limit": 20})
            fill_history = client.get("/v1/fills/history", params={"limit": 20})
            market_bars = client.get("/v1/market/bars", params={"limit": 1})
            equity_curve = client.get("/v1/portfolio/equity-curve", params={"limit": 20})
            replay_events = client.get("/v1/diagnostics/replay-events", params={"limit": 20})

        assert ready.status_code == 200
        assert ready.json() == {
            "trader_run_id": None,
            "instance_id": None,
            "account_id": settings.account_id,
            "control_state": "normal",
            "strategy_enabled": True,
            "kill_switch_active": False,
            "protection_mode_active": False,
            "ready": False,
            "status": "not_ready",
            "health_status": "unknown",
            "lifecycle_status": "stopped",
            "market_data_fresh": False,
            "market_state_available": False,
            "latest_final_bar_time": None,
            "current_trading_phase": None,
            "lease_owner_instance_id": None,
            "lease_expires_at": None,
            "last_heartbeat_at": None,
            "fencing_token": None,
            "last_cancel_all_at": None,
            "cancel_all_token": 0,
            "message": (
                "Control-plane schema is missing required tables: "
                "trader_account_leases, trader_controls, trader_runtime_status. "
                "Run `.venv/bin/alembic -c migrations/alembic.ini upgrade head` first."
            ),
        }

        assert status.status_code == 200
        assert status.json() == {
            **ready.json(),
            "service": settings.app_name,
            "env": settings.env,
            "execution_mode": settings.execution_mode,
            "exchange": settings.exchange,
            "symbols": settings.symbols,
            "symbol_names": settings.symbol_names,
        }

        assert positions.status_code == 200
        assert positions.json() == {
            "account_id": settings.account_id,
            "positions": [],
        }

        assert active_orders.status_code == 200
        assert active_orders.json() == {
            "account_id": settings.account_id,
            "orders": [],
        }

        assert order_history.status_code == 200
        assert order_history.json() == {
            "filters": {
                "start_time": None,
                "end_time": None,
                "trader_run_id": None,
                "account_id": settings.account_id,
                "symbol": None,
                "status": None,
                "limit": 20,
            },
            "count": 0,
            "orders": [],
        }

        assert fill_history.status_code == 200
        assert fill_history.json() == {
            "filters": {
                "start_time": None,
                "end_time": None,
                "trader_run_id": None,
                "account_id": settings.account_id,
                "symbol": None,
                "order_id": None,
                "limit": 20,
            },
            "count": 0,
            "fills": [],
        }

        assert market_bars.status_code == 200
        assert market_bars.json() == {
            "symbol": "600036.SH",
            "timeframe": "15m",
            "count": 1,
            "source": "eastmoney_historical",
            "bars": [
                {
                    "time": "2026-04-02T09:45:00+08:00",
                    "open": 39.4,
                    "high": 39.52,
                    "low": 39.35,
                    "close": 39.48,
                    "volume": 118000.0,
                }
            ],
        }

        assert equity_curve.status_code == 200
        assert equity_curve.json() == {
            "account_id": settings.account_id,
            "symbol": "600036.SH",
            "timeframe": "15m",
            "count": 0,
            "source": "balance_snapshots_plus_portfolio_market_bars",
            "scope": "account_portfolio",
            "anchor_symbol": "600036.SH",
            "valuation_symbols": ["600036.SH"],
            "points": [],
        }

        assert replay_events.status_code == 200
        assert replay_events.json()["filters"]["account_id"] == settings.account_id
        assert replay_events.json()["count"] == 0
        assert replay_events.json()["events"] == []
        assert inspect(engine).get_table_names() == []
    finally:
        get_settings.cache_clear()
        engine.dispose()
