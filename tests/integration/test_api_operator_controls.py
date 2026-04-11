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
from src.domain.portfolio import BalanceSnapshot, Position, PositionStatus
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


def _balance_snapshot(
    *,
    snapshot_time: datetime,
    total: str,
    available: str,
    locked: str,
) -> BalanceSnapshot:
    return BalanceSnapshot(
        account_id="paper_account_001",
        exchange="cn_equity",
        asset="CNY",
        total=Decimal(total),
        available=Decimal(available),
        locked=Decimal(locked),
        snapshot_time=snapshot_time,
        created_at=snapshot_time,
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
        repositories.balance_snapshots.save(
            _balance_snapshot(
                snapshot_time=NOW - timedelta(minutes=2),
                total="98000",
                available="97500",
                locked="500",
            )
        )
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
        balance_summary = client.get("/v1/balance/summary")
        positions = client.get("/v1/positions")
        active_orders = client.get("/v1/orders/active")

        assert live.status_code == 200
        assert live.json()["status"] == "alive"
        assert ready.json()["status"] == "ready"
        assert ready.json()["lease_owner_instance_id"] == "instance-A"
        assert status.json()["control_state"] == "normal"
        assert status.json()["trader_run_id"] == "runtime-run-001"
        assert balance_summary.status_code == 200
        assert balance_summary.json()["cash_balance"] == "98000"
        assert balance_summary.json()["available_cash"] == "97500"
        assert balance_summary.json()["frozen_cash"] == "500"
        assert balance_summary.json()["market_value"] == "11850"
        assert balance_summary.json()["equity"] == "109850"
        assert balance_summary.json()["position_count"] == 1
        assert "账户权益由现金余额和持仓市值共同组成" in balance_summary.json()["summary_message"]
        assert len(positions.json()["positions"]) == 1
        assert len(active_orders.json()["orders"]) == 2

        pause = client.post("/v1/controls/strategy/pause")
        assert pause.status_code == 200
        assert pause.json()["accepted"] is True
        assert pause.json()["control_state"] == "strategy_paused"
        assert pause.json()["effective_scope"] == "strategy_submission"
        assert pause.json()["reason_code"] == "OPERATOR_REQUEST"

        enable_kill_switch = client.post("/v1/controls/kill-switch/enable")
        assert enable_kill_switch.status_code == 200
        assert enable_kill_switch.json()["control_state"] == "kill_switch"
        assert enable_kill_switch.json()["effective_scope"] == "opening_order_gate"
        assert enable_kill_switch.json()["reason_code"] == "OPERATOR_REQUEST"

        cancel_all = client.post("/v1/controls/cancel-all")
        assert cancel_all.status_code == 200
        assert cancel_all.json()["requested_order_count"] == 2
        assert cancel_all.json()["cancelled_order_count"] == 1
        assert cancel_all.json()["skipped_order_count"] == 1
        assert cancel_all.json()["control_state"] == "kill_switch"
        assert cancel_all.json()["effective_scope"] == "active_orders"
        assert cancel_all.json()["reason_code"] == "OPERATOR_REQUEST"
        assert [event.event_name for event in alert_sink.events] == [
            "control.kill_switch_enabled",
            "control.cancel_all_requested",
        ]

        remaining_active = client.get("/v1/orders/active")
        assert remaining_active.status_code == 200
        assert len(remaining_active.json()["orders"]) == 1
        assert remaining_active.json()["orders"][0]["reduce_only"] is True

    engine.dispose()


def test_api_inspects_symbol_layers_and_validation_state(tmp_path: Path) -> None:
    from apps.api.main import create_app

    database_url = _database_url(tmp_path)
    settings = _settings(database_url)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        runtime_symbol = client.get("/v1/symbols/inspect", params={"symbol": "600036.sh"})
        supported_symbol = client.get("/v1/symbols/inspect", params={"symbol": "000001.SZ"})
        observed_only_symbol = client.get("/v1/symbols/inspect", params={"symbol": "300750.SZ"})
        invalid_symbol = client.get("/v1/symbols/inspect", params={"symbol": "abc"})

    assert runtime_symbol.status_code == 200
    assert runtime_symbol.json() == {
        "raw_input": "600036.sh",
        "normalized_symbol": "600036.SH",
        "format_valid": True,
        "market": "a_share",
        "market_label": "A 股",
        "venue": "SH",
        "venue_label": "上海证券交易所",
        "display_name": "招商银行",
        "name_status": "available",
        "layers": {
            "observed": True,
            "supported": True,
            "runtime_enabled": True,
        },
        "reason_code": "SYMBOL_RUNTIME_ENABLED",
        "message": "该股票代码已进入当前 trader 运行范围，可能影响自动交易判断。",
        "runtime_activation": {
            "requires_confirmation": True,
            "phase": "phase_2_runtime_request",
            "can_apply_now": False,
            "effective_scope": "runtime_symbols",
            "activation_mode": "already_live",
            "request_status": "already_enabled",
            "last_requested_at": None,
            "requested_runtime_symbols_preview": ["600036.SH"],
            "message": "该股票代码已在当前 runtime 范围内，无需再次申请。",
        },
    }

    assert supported_symbol.status_code == 200
    assert supported_symbol.json()["layers"] == {
        "observed": True,
        "supported": True,
        "runtime_enabled": False,
    }
    assert supported_symbol.json()["reason_code"] == "SYMBOL_SUPPORTED_NOT_RUNTIME"
    assert supported_symbol.json()["runtime_activation"] == {
        "requires_confirmation": True,
        "phase": "phase_2_runtime_request",
        "can_apply_now": True,
        "effective_scope": "runtime_symbols",
        "activation_mode": "requires_reload",
        "request_status": "not_requested",
        "last_requested_at": None,
        "requested_runtime_symbols_preview": ["600036.SH", "000001.SZ"],
        "message": "确认后可以记录运行范围变更请求，但需要重载 trader 才会真正生效。",
    }

    assert observed_only_symbol.status_code == 200
    assert observed_only_symbol.json()["display_name"] is None
    assert observed_only_symbol.json()["name_status"] == "missing"
    assert observed_only_symbol.json()["layers"] == {
        "observed": True,
        "supported": False,
        "runtime_enabled": False,
    }
    assert observed_only_symbol.json()["reason_code"] == "SYMBOL_OBSERVED_ONLY"
    assert observed_only_symbol.json()["runtime_activation"] == {
        "requires_confirmation": True,
        "phase": "phase_2_runtime_request",
        "can_apply_now": False,
        "effective_scope": "runtime_symbols",
        "activation_mode": "unavailable",
        "request_status": "unsupported_symbol",
        "last_requested_at": None,
        "requested_runtime_symbols_preview": ["600036.SH"],
        "message": "该股票代码尚未进入 supported_symbols，暂时不能申请加入 runtime。",
    }

    assert invalid_symbol.status_code == 200
    assert invalid_symbol.json() == {
        "raw_input": "abc",
        "normalized_symbol": "ABC",
        "format_valid": False,
        "market": "unknown",
        "market_label": "待确认",
        "venue": None,
        "venue_label": "待确认",
        "display_name": None,
        "name_status": "missing",
        "layers": {
            "observed": True,
            "supported": False,
            "runtime_enabled": False,
        },
        "reason_code": "INVALID_SYMBOL_FORMAT",
        "message": "代码格式不符合 A 股约定，请使用 6 位数字加 .SH 或 .SZ 后缀。",
        "runtime_activation": {
            "requires_confirmation": True,
            "phase": "phase_2_runtime_request",
            "can_apply_now": False,
            "effective_scope": "runtime_symbols",
            "activation_mode": "unavailable",
            "request_status": "invalid_symbol",
            "last_requested_at": None,
            "requested_runtime_symbols_preview": ["600036.SH"],
            "message": "代码格式不合法，暂时不能进入 runtime 范围申请。",
        },
    }


def test_api_records_runtime_symbol_requests_and_exposes_pending_reload_state(
    tmp_path: Path,
) -> None:
    from apps.api.main import create_app

    database_url = _database_url(tmp_path)
    settings = _settings(database_url)
    upgrade_database(database_url)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        request = client.post(
            "/v1/symbols/runtime-requests",
            json={
                "symbol": "000001.SZ",
                "confirm": True,
            },
        )
        inspected = client.get("/v1/symbols/inspect", params={"symbol": "000001.SZ"})

    request_payload = request.json()
    assert request.status_code == 200
    assert request_payload == {
        "accepted": True,
        "symbol": "000001.SZ",
        "normalized_symbol": "000001.SZ",
        "control_state": "normal",
        "trader_run_id": None,
        "instance_id": None,
        "effective_at": request_payload["effective_at"],
        "effective_scope": "runtime_symbols",
        "activation_mode": "requires_reload",
        "request_status": "pending_reload",
        "message": "已记录运行范围变更请求；需要重载 trader 后才会真正进入运行范围。",
        "reason_code": "RUNTIME_CHANGE_REQUIRES_RELOAD",
        "current_runtime_symbols": ["600036.SH"],
        "requested_runtime_symbols": ["600036.SH", "000001.SZ"],
        "last_requested_at": request_payload["last_requested_at"],
    }
    assert request_payload["last_requested_at"] is not None

    assert inspected.status_code == 200
    assert inspected.json()["runtime_activation"] == {
        "requires_confirmation": True,
        "phase": "phase_2_runtime_request",
        "can_apply_now": False,
        "effective_scope": "runtime_symbols",
        "activation_mode": "requires_reload",
        "request_status": "pending_reload",
        "last_requested_at": request_payload["last_requested_at"],
        "requested_runtime_symbols_preview": ["600036.SH", "000001.SZ"],
        "message": "该股票代码的运行范围变更请求已记录，等待 trader 重载后生效。",
    }


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
