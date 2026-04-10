from __future__ import annotations

import os
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from apps.api.control_plane import ApiControlPlaneService
from apps.trader.control_plane import (
    TraderControlPlaneStore,
    TraderRuntimeStatusSnapshot,
)
from fastapi.testclient import TestClient
from src.config.settings import Settings
from src.domain.execution import (
    OrderIntent,
    OrderIntentStatus,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
    create_order_from_intent,
)
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.portfolio import Position, PositionStatus
from src.domain.risk import RiskControlState
from src.domain.strategy import Signal, SignalType
from src.infra.db import (
    SqlAlchemyRepositories,
    create_database_engine,
    create_session_factory,
)
from src.infra.observability import AlertRouter, RecordingAlertSink, SignalArkObservability
from tests.support.migrations import upgrade_database

SHANGHAI = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 4, 1, 13, 0, tzinfo=SHANGHAI)
MARKET_STATE = MarketStateSnapshot(
    trade_date=NOW.date(),
    previous_close=Decimal("39.47"),
    upper_limit_price=Decimal("43.42"),
    lower_limit_price=Decimal("35.52"),
    trading_phase=TradingPhase.CONTINUOUS_AUCTION,
    suspension_status=SuspensionStatus.ACTIVE,
)

os.environ.setdefault(
    "SIGNALARK_POSTGRES_DSN", "sqlite+pysqlite:////tmp/signalark-phase6b-api.sqlite3"
)


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'phase6b_api.sqlite3'}"


def _settings(database_url: str) -> Settings:
    return Settings(
        postgres_dsn=database_url,
        api_port=8010,
    )


def _signal(*, signal_id: UUID, target_position: Decimal) -> Signal:
    return Signal(
        id=signal_id,
        strategy_id="baseline_momentum_v1",
        trader_run_id=UUID("11111111-1111-4111-8111-111111111111"),
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        signal_type=SignalType.REBALANCE,
        target_position=target_position,
        event_time=NOW - timedelta(minutes=5),
        created_at=NOW - timedelta(minutes=5) + timedelta(seconds=1),
    )


def _position() -> Position:
    return Position(
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        qty=Decimal("300"),
        sellable_qty=Decimal("300"),
        avg_entry_price=Decimal("39.20"),
        mark_price=Decimal("39.50"),
        unrealized_pnl=Decimal("90"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.OPEN,
        updated_at=NOW - timedelta(minutes=10),
    )


def _active_order_intent(
    *,
    signal: Signal,
    order_intent_id: UUID,
    side: OrderSide,
    qty: Decimal,
    reduce_only: bool,
    created_at: datetime,
) -> OrderIntent:
    return OrderIntent(
        id=order_intent_id,
        signal_id=signal.id,
        strategy_id=signal.strategy_id,
        trader_run_id=signal.trader_run_id,
        account_id=signal.account_id,
        exchange=signal.exchange,
        symbol=signal.symbol,
        side=side,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        qty=qty,
        decision_price=Decimal("39.50"),
        reduce_only=reduce_only,
        market_context_json=MARKET_STATE,
        idempotency_key=f"intent:{order_intent_id}",
        status=OrderIntentStatus.SUBMITTED,
        created_at=created_at,
    )


def test_api_exposes_status_controls_and_cancel_all_boundaries(tmp_path: Path) -> None:
    from apps.api.main import create_app

    database_url = _database_url(tmp_path)
    settings = _settings(database_url)
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory, clock=lambda: NOW)
    lease_result = control_store.acquire_lease(
        account_id=settings.account_id,
        instance_id="instance-A",
        ttl_seconds=settings.lease_ttl_seconds,
        now=NOW,
    )
    control_store.save_runtime_status(
        TraderRuntimeStatusSnapshot(
            account_id=settings.account_id,
            trader_run_id="runtime-run-001",
            instance_id="instance-A",
            lifecycle_status="running",
            health_status="alive",
            readiness_status="ready",
            control_state=RiskControlState.NORMAL,
            strategy_enabled=True,
            kill_switch_active=False,
            protection_mode_active=False,
            market_data_fresh=True,
            latest_final_bar_time=NOW - timedelta(seconds=5),
            current_trading_phase=TradingPhase.CONTINUOUS_AUCTION.value,
            fencing_token=lease_result.snapshot.fencing_token,
            last_status_message="runtime_ready",
            updated_at=NOW,
        )
    )
    with session_factory.begin() as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        repositories.positions.save(_position())
        buy_signal = _signal(
            signal_id=UUID("22222222-2222-4222-8222-222222222222"),
            target_position=Decimal("400"),
        )
        reduce_signal = _signal(
            signal_id=UUID("33333333-3333-4333-8333-333333333333"),
            target_position=Decimal("0"),
        )
        repositories.signals.save(buy_signal)
        repositories.signals.save(reduce_signal)
        buy_intent = _active_order_intent(
            signal=buy_signal,
            order_intent_id=UUID("44444444-4444-4444-8444-444444444444"),
            side=OrderSide.BUY,
            qty=Decimal("100"),
            reduce_only=False,
            created_at=NOW - timedelta(minutes=4),
        )
        reduce_only_intent = _active_order_intent(
            signal=reduce_signal,
            order_intent_id=UUID("55555555-5555-4555-8555-555555555555"),
            side=OrderSide.SELL,
            qty=Decimal("100"),
            reduce_only=True,
            created_at=NOW - timedelta(minutes=3),
        )
        repositories.order_intents.save(buy_intent)
        repositories.order_intents.save(reduce_only_intent)
        repositories.orders.save(
            create_order_from_intent(
                buy_intent,
                status=OrderStatus.NEW,
                submitted_at=NOW - timedelta(minutes=4),
            )
        )
        repositories.orders.save(
            create_order_from_intent(
                reduce_only_intent,
                status=OrderStatus.NEW,
                submitted_at=NOW - timedelta(minutes=3),
            )
        )

    alert_sink = RecordingAlertSink()
    service = ApiControlPlaneService(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        observability=SignalArkObservability(
            service="tests",
            alert_router=AlertRouter((alert_sink,), clock=lambda: NOW),
            clock=lambda: NOW,
        ),
    )
    app = create_app(settings=settings, control_plane_service=service)

    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        status = client.get("/v1/status")
        positions = client.get("/v1/positions")
        active_orders = client.get("/v1/orders/active")

        assert live.status_code == 200
        assert live.json()["status"] == "alive"
        assert ready.json()["status"] == "ready"
        assert ready.json()["lease_owner_instance_id"] == "instance-A"
        assert status.json()["control_state"] == "normal"
        assert status.json()["trader_run_id"] == "runtime-run-001"
        assert len(positions.json()["positions"]) == 1
        assert len(active_orders.json()["orders"]) == 2

        pause = client.post("/v1/controls/strategy/pause")
        assert pause.status_code == 200
        assert pause.json()["accepted"] is True
        assert pause.json()["control_state"] == "strategy_paused"

        enable_kill_switch = client.post("/v1/controls/kill-switch/enable")
        assert enable_kill_switch.status_code == 200
        assert enable_kill_switch.json()["control_state"] == "kill_switch"

        cancel_all = client.post("/v1/controls/cancel-all")
        assert cancel_all.status_code == 200
        assert cancel_all.json()["requested_order_count"] == 2
        assert cancel_all.json()["cancelled_order_count"] == 1
        assert cancel_all.json()["skipped_order_count"] == 1
        assert cancel_all.json()["control_state"] == "kill_switch"
        assert [event.event_name for event in alert_sink.events] == [
            "control.kill_switch_enabled",
            "control.cancel_all_requested",
        ]

        remaining_active = client.get("/v1/orders/active")
        assert remaining_active.status_code == 200
        assert len(remaining_active.json()["orders"]) == 1
        assert remaining_active.json()["orders"][0]["reduce_only"] is True

    engine.dispose()


def test_api_allows_configured_frontend_origin_via_cors_preflight(tmp_path: Path) -> None:
    from apps.api.main import create_app

    database_url = _database_url(tmp_path)
    settings = Settings(
        postgres_dsn=database_url,
        api_port=8010,
        api_cors_allowed_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:4173",
        ],
    )

    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.options(
            "/v1/status",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "GET" in response.headers["access-control-allow-methods"]


def test_api_allows_put_research_ai_settings_via_cors_preflight(tmp_path: Path) -> None:
    from apps.api.main import create_app

    database_url = _database_url(tmp_path)
    settings = Settings(
        postgres_dsn=database_url,
        api_port=8010,
        api_cors_allowed_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:4173",
        ],
    )

    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.options(
            "/v1/research/ai-settings",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "PUT" in response.headers["access-control-allow-methods"]
