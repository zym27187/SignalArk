from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from apps.api.control_plane import ApiControlPlaneService
from apps.api.main import create_app
from apps.trader.control_plane import TraderControlPlaneStore
from fastapi.testclient import TestClient
from src.config.settings import Settings
from src.domain.execution import (
    Fill,
    LiquidityType,
    Order,
    OrderIntent,
    OrderIntentStatus,
    OrderSide,
    OrderStatus,
    OrderType,
    RiskDecision,
    TimeInForce,
)
from src.domain.strategy import Signal, SignalType
from src.infra.db import SqlAlchemyRepositories, create_database_engine, create_session_factory
from tests.support.migrations import upgrade_database

SHANGHAI = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 4, 3, 10, 30, tzinfo=SHANGHAI)
PRIMARY_RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
SECONDARY_RUN_ID = UUID("22222222-2222-4222-8222-222222222222")


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'api_execution_history.sqlite3'}"


def _settings(database_url: str) -> Settings:
    return Settings(
        postgres_dsn=database_url,
        symbols=["600036.SH", "000001.SZ"],
    )


def _signal(*, signal_id: UUID, trader_run_id: UUID, symbol: str, event_time: datetime) -> Signal:
    return Signal(
        id=signal_id,
        strategy_id="baseline_momentum_v1",
        trader_run_id=trader_run_id,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol=symbol,
        timeframe="15m",
        signal_type=SignalType.REBALANCE,
        target_position=Decimal("100"),
        event_time=event_time,
        created_at=event_time + timedelta(seconds=1),
    )


def _order_intent(
    *,
    order_intent_id: UUID,
    signal: Signal,
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
        decision_price=Decimal("39.80"),
        reduce_only=reduce_only,
        market_context_json={},
        idempotency_key=f"intent:{order_intent_id}",
        status=OrderIntentStatus.SUBMITTED,
        risk_decision=RiskDecision.ALLOW,
        risk_reason=None,
        created_at=created_at,
    )


def _order(
    *,
    order_id: UUID,
    order_intent: OrderIntent,
    status: OrderStatus,
    submitted_at: datetime,
    updated_at: datetime,
    filled_qty: Decimal,
    avg_fill_price: Decimal | None,
) -> Order:
    return Order(
        id=order_id,
        order_intent_id=order_intent.id,
        trader_run_id=order_intent.trader_run_id,
        exchange_order_id=f"paper-order-{order_id}",
        account_id=order_intent.account_id,
        exchange=order_intent.exchange,
        symbol=order_intent.symbol,
        side=order_intent.side,
        order_type=order_intent.order_type,
        time_in_force=order_intent.time_in_force,
        qty=order_intent.qty,
        price=None,
        filled_qty=filled_qty,
        avg_fill_price=avg_fill_price,
        status=status,
        submitted_at=submitted_at,
        updated_at=updated_at,
        last_error_code=None,
        last_error_message=None,
    )


def _fill(
    *,
    fill_id: UUID,
    order: Order,
    price: Decimal,
    fee: Decimal,
    fill_time: datetime,
) -> Fill:
    return Fill(
        id=fill_id,
        order_id=order.id,
        trader_run_id=order.trader_run_id,
        exchange_fill_id=f"paper-fill-{fill_id}",
        account_id=order.account_id,
        exchange=order.exchange,
        symbol=order.symbol,
        side=order.side,
        qty=order.filled_qty,
        price=price,
        fee=fee,
        fee_asset="CNY",
        liquidity_type=LiquidityType.TAKER,
        fill_time=fill_time,
        created_at=fill_time,
    )


def test_api_exposes_historical_orders_and_fills_with_shared_filters(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    settings = _settings(database_url)
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory, clock=lambda: NOW)

    primary_signal = _signal(
        signal_id=UUID("33333333-3333-4333-8333-333333333333"),
        trader_run_id=PRIMARY_RUN_ID,
        symbol="600036.SH",
        event_time=NOW - timedelta(minutes=6),
    )
    secondary_signal = _signal(
        signal_id=UUID("44444444-4444-4444-8444-444444444444"),
        trader_run_id=SECONDARY_RUN_ID,
        symbol="000001.SZ",
        event_time=NOW - timedelta(minutes=12),
    )
    primary_intent = _order_intent(
        order_intent_id=UUID("55555555-5555-4555-8555-555555555555"),
        signal=primary_signal,
        side=OrderSide.BUY,
        qty=Decimal("200"),
        reduce_only=False,
        created_at=NOW - timedelta(minutes=5, seconds=30),
    )
    secondary_intent = _order_intent(
        order_intent_id=UUID("66666666-6666-4666-8666-666666666666"),
        signal=secondary_signal,
        side=OrderSide.SELL,
        qty=Decimal("100"),
        reduce_only=True,
        created_at=NOW - timedelta(minutes=11, seconds=30),
    )
    primary_order = _order(
        order_id=UUID("77777777-7777-4777-8777-777777777777"),
        order_intent=primary_intent,
        status=OrderStatus.FILLED,
        submitted_at=NOW - timedelta(minutes=5),
        updated_at=NOW - timedelta(minutes=4),
        filled_qty=Decimal("200"),
        avg_fill_price=Decimal("39.88"),
    )
    secondary_order = _order(
        order_id=UUID("88888888-8888-4888-8888-888888888888"),
        order_intent=secondary_intent,
        status=OrderStatus.CANCELED,
        submitted_at=NOW - timedelta(minutes=11),
        updated_at=NOW - timedelta(minutes=10),
        filled_qty=Decimal("0"),
        avg_fill_price=None,
    )
    primary_fill = _fill(
        fill_id=UUID("99999999-9999-4999-8999-999999999999"),
        order=primary_order,
        price=Decimal("39.88"),
        fee=Decimal("1.50"),
        fill_time=NOW - timedelta(minutes=4),
    )

    with session_factory.begin() as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        repositories.signals.save(primary_signal)
        repositories.signals.save(secondary_signal)
        repositories.order_intents.save(primary_intent)
        repositories.order_intents.save(secondary_intent)
        repositories.orders.save(primary_order)
        repositories.orders.save(secondary_order)
        repositories.fills.save(primary_fill)

    service = ApiControlPlaneService(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
    )
    app = create_app(settings=settings, control_plane_service=service)

    try:
        with TestClient(app) as client:
            order_history = client.get(
                "/v1/orders/history",
                params={
                    "start_time": (NOW - timedelta(minutes=5)).isoformat(),
                    "end_time": (NOW - timedelta(minutes=3)).isoformat(),
                    "trader_run_id": str(PRIMARY_RUN_ID),
                    "symbol": "600036.SH",
                    "status": "filled",
                    "limit": 20,
                },
            )
            fill_history = client.get(
                "/v1/fills/history",
                params={
                    "start_time": (NOW - timedelta(minutes=5)).isoformat(),
                    "end_time": (NOW - timedelta(minutes=3)).isoformat(),
                    "trader_run_id": str(PRIMARY_RUN_ID),
                    "symbol": "600036.SH",
                    "order_id": str(primary_order.id),
                    "limit": 20,
                },
            )

        assert order_history.status_code == 200
        order_payload = order_history.json()
        assert order_payload["count"] == 1
        assert order_payload["filters"]["symbol"] == "600036.SH"
        assert order_payload["filters"]["status"] == "FILLED"
        assert order_payload["orders"][0]["order_id"] == str(primary_order.id)
        assert order_payload["orders"][0]["reduce_only"] is False
        assert order_payload["orders"][0]["risk_decision"] == "ALLOW"

        assert fill_history.status_code == 200
        fill_payload = fill_history.json()
        assert fill_payload["count"] == 1
        assert fill_payload["filters"]["order_id"] == str(primary_order.id)
        assert fill_payload["fills"][0]["fill_id"] == str(primary_fill.id)
        assert fill_payload["fills"][0]["fee"] == "1.5000000000"
        assert fill_payload["fills"][0]["reduce_only"] is False
    finally:
        engine.dispose()
