from __future__ import annotations

import os
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from apps.api.control_plane import ApiControlPlaneService
from apps.trader.control_plane import TraderControlPlaneStore
from fastapi.testclient import TestClient
from src.config.settings import Settings
from src.domain.execution import (
    Fill,
    LiquidityType,
    Order,
    OrderIntent,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from src.domain.market import MarketStateSnapshot, NormalizedBar, SuspensionStatus, TradingPhase
from src.domain.portfolio import BalanceSnapshot
from src.domain.strategy import Signal, SignalType
from src.infra.db import (
    SqlAlchemyRepositories,
    create_database_engine,
    create_session_factory,
)
from tests.support.migrations import upgrade_database

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 2, 9, 45, tzinfo=SHANGHAI)
BUY_TIME = BASE_TIME + timedelta(minutes=15)
MARKET_STATE = MarketStateSnapshot(
    trade_date=BASE_TIME.date(),
    previous_close=Decimal("39.40"),
    upper_limit_price=Decimal("43.34"),
    lower_limit_price=Decimal("35.46"),
    trading_phase=TradingPhase.CONTINUOUS_AUCTION,
    suspension_status=SuspensionStatus.ACTIVE,
)


class FakeHistoricalBarGateway:
    def __init__(self, bars_by_timeframe: dict[str, list[NormalizedBar]]) -> None:
        self._bars_by_timeframe = {
            timeframe: list(bars)
            for timeframe, bars in bars_by_timeframe.items()
        }

    async def fetch_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_bars: int | None = None,
    ) -> list[NormalizedBar]:
        assert symbol == "600036.SH"
        del start_time, end_time
        bars = list(self._bars_by_timeframe[timeframe])
        if max_bars is not None:
            bars = bars[-max_bars:]
        return bars

    async def aclose(self) -> None:
        return None


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'api_market.sqlite3'}"


def _settings(database_url: str) -> Settings:
    return Settings(postgres_dsn=database_url)


def _bar(*, index: int, close: str, timeframe: str = "15m") -> NormalizedBar:
    step = timedelta(minutes=15 if timeframe == "15m" else 60)
    bar_end_time = BASE_TIME + step * index
    return NormalizedBar(
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe=timeframe,
        bar_start_time=bar_end_time - step,
        bar_end_time=bar_end_time,
        ingest_time=bar_end_time + timedelta(minutes=1),
        open="39.45",
        high="39.85",
        low="39.30",
        close=close,
        volume="120000",
        quote_volume="4740000",
        closed=True,
        final=True,
        source_kind="historical",
        market_state=MARKET_STATE,
    )


def _signal() -> Signal:
    return Signal(
        id=UUID("11111111-1111-4111-8111-111111111111"),
        strategy_id="baseline_momentum_v1",
        trader_run_id=UUID("22222222-2222-4222-8222-222222222222"),
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        signal_type=SignalType.REBALANCE,
        target_position=Decimal("100"),
        event_time=BUY_TIME,
        created_at=BUY_TIME,
    )


def _order_intent(signal: Signal) -> OrderIntent:
    return OrderIntent(
        id=UUID("33333333-3333-4333-8333-333333333333"),
        signal_id=signal.id,
        strategy_id=signal.strategy_id,
        trader_run_id=signal.trader_run_id,
        account_id=signal.account_id,
        exchange=signal.exchange,
        symbol=signal.symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        qty=Decimal("100"),
        decision_price=Decimal("39.60"),
        reduce_only=False,
        market_context_json=MARKET_STATE,
        idempotency_key="intent:api-market:001",
        created_at=BUY_TIME,
    )


def _order(order_intent: OrderIntent) -> Order:
    return Order(
        id=UUID("44444444-4444-4444-8444-444444444444"),
        order_intent_id=order_intent.id,
        trader_run_id=order_intent.trader_run_id,
        exchange_order_id="paper-order-001",
        account_id=order_intent.account_id,
        exchange=order_intent.exchange,
        symbol=order_intent.symbol,
        side=order_intent.side,
        order_type=order_intent.order_type,
        time_in_force=order_intent.time_in_force,
        qty=order_intent.qty,
        filled_qty=order_intent.qty,
        avg_fill_price=Decimal("39.60"),
        status=OrderStatus.FILLED,
        submitted_at=BUY_TIME,
        updated_at=BUY_TIME,
    )


def _fill(order: Order) -> Fill:
    return Fill(
        id=UUID("55555555-5555-4555-8555-555555555555"),
        order_id=order.id,
        trader_run_id=order.trader_run_id,
        exchange_fill_id="paper-fill-001",
        account_id=order.account_id,
        exchange=order.exchange,
        symbol=order.symbol,
        side=order.side,
        qty=Decimal("100"),
        price=Decimal("39.60"),
        fee=Decimal("1.00"),
        fee_asset="CNY",
        liquidity_type=LiquidityType.TAKER,
        fill_time=BUY_TIME,
        created_at=BUY_TIME,
    )


def _balance_snapshot(*, snapshot_time: datetime, total: str) -> BalanceSnapshot:
    total_amount = Decimal(total)
    return BalanceSnapshot(
        account_id="paper_account_001",
        exchange="cn_equity",
        asset="CNY",
        total=total_amount,
        available=total_amount,
        locked=Decimal("0"),
        snapshot_time=snapshot_time,
        created_at=snapshot_time,
    )


def test_api_market_endpoints_return_live_bars_and_reconstructed_equity_curve(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv("SIGNALARK_POSTGRES_DSN", database_url)
    from src.config import get_settings

    get_settings.cache_clear()

    from apps.api.main import create_app

    settings = _settings(database_url)
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory)

    with session_factory.begin() as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        repositories.balance_snapshots.save(
            _balance_snapshot(snapshot_time=BASE_TIME - timedelta(minutes=15), total="100000")
        )
        signal = repositories.signals.save(_signal())
        order_intent = repositories.order_intents.save(_order_intent(signal))
        order = repositories.orders.save(_order(order_intent))
        repositories.fills.save(_fill(order))
        repositories.balance_snapshots.save(
            _balance_snapshot(snapshot_time=BUY_TIME, total="96039")
        )

    bars_15m = [
        _bar(index=0, close="39.50"),
        _bar(index=1, close="39.60"),
        _bar(index=2, close="39.80"),
    ]
    bars_1h = [
        _bar(index=0, close="39.52", timeframe="1h"),
        _bar(index=1, close="39.88", timeframe="1h"),
    ]
    service = ApiControlPlaneService(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        market_gateway_factory=lambda: FakeHistoricalBarGateway(
            {
                "15m": bars_15m,
                "1h": bars_1h,
            }
        ),
    )
    app = create_app(settings=settings, control_plane_service=service)

    try:
        with TestClient(app) as client:
            bars_response = client.get("/v1/market/bars", params={"limit": 3})
            curve_response = client.get("/v1/portfolio/equity-curve", params={"limit": 3})
            hourly_bars_response = client.get(
                "/v1/market/bars",
                params={"timeframe": "1h", "limit": 2},
            )

        assert bars_response.status_code == 200
        assert bars_response.json() == {
            "symbol": "600036.SH",
            "timeframe": "15m",
            "count": 3,
            "source": "eastmoney_historical",
            "bars": [
                {
                    "time": "2026-04-02T09:45:00+08:00",
                    "open": 39.45,
                    "high": 39.85,
                    "low": 39.3,
                    "close": 39.5,
                    "volume": 120000.0,
                },
                {
                    "time": "2026-04-02T10:00:00+08:00",
                    "open": 39.45,
                    "high": 39.85,
                    "low": 39.3,
                    "close": 39.6,
                    "volume": 120000.0,
                },
                {
                    "time": "2026-04-02T10:15:00+08:00",
                    "open": 39.45,
                    "high": 39.85,
                    "low": 39.3,
                    "close": 39.8,
                    "volume": 120000.0,
                },
            ],
        }

        assert curve_response.status_code == 200
        assert curve_response.json() == {
            "account_id": settings.account_id,
            "symbol": "600036.SH",
            "timeframe": "15m",
            "count": 3,
            "source": "balance_snapshots_plus_market_bars",
            "points": [
                {
                    "time": "2026-04-02T09:45:00+08:00",
                    "value": 100000.0,
                    "baseline": 100000.0,
                },
                {
                    "time": "2026-04-02T10:00:00+08:00",
                    "value": 99999.0,
                    "baseline": 100000.0,
                },
                {
                    "time": "2026-04-02T10:15:00+08:00",
                    "value": 100019.0,
                    "baseline": 100000.0,
                },
            ],
        }

        assert hourly_bars_response.status_code == 200
        assert hourly_bars_response.json()["timeframe"] == "1h"
        assert hourly_bars_response.json()["count"] == 2
        assert hourly_bars_response.json()["bars"][1]["time"] == "2026-04-02T10:45:00+08:00"
    finally:
        get_settings.cache_clear()
        os.environ.pop("SIGNALARK_POSTGRES_DSN", None)
        engine.dispose()
