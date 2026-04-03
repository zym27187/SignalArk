from __future__ import annotations

import os
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from apps.api.control_plane import ApiControlPlaneService
from apps.trader.control_plane import TraderControlPlaneStore, TraderRuntimeStatusSnapshot
from apps.trader.runtime import TraderRuntimeState
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
from src.domain.risk import RiskControlState
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
DEFAULT_SIGNAL_ID = UUID("11111111-1111-4111-8111-111111111111")
DEFAULT_TRADER_RUN_ID = UUID("22222222-2222-4222-8222-222222222222")
DEFAULT_ORDER_INTENT_ID = UUID("33333333-3333-4333-8333-333333333333")
DEFAULT_ORDER_ID = UUID("44444444-4444-4444-8444-444444444444")
DEFAULT_FILL_ID = UUID("55555555-5555-4555-8555-555555555555")


class FakeHistoricalBarGateway:
    def __init__(
        self,
        bars_by_request: dict[tuple[str, str], list[NormalizedBar]],
    ) -> None:
        self._bars_by_request = {
            (symbol, timeframe): list(bars) for (symbol, timeframe), bars in bars_by_request.items()
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
        del start_time, end_time
        bars = list(self._bars_by_request[(symbol, timeframe)])
        if max_bars is not None:
            bars = bars[-max_bars:]
        return bars

    async def aclose(self) -> None:
        return None


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'api_market.sqlite3'}"


def _settings(database_url: str) -> Settings:
    return Settings(postgres_dsn=database_url)


def _bar(
    *,
    index: int,
    close: str,
    symbol: str = "600036.SH",
    timeframe: str = "15m",
    open_price: str = "39.45",
    high: str = "39.85",
    low: str = "39.30",
    volume: str = "120000",
    quote_volume: str = "4740000",
) -> NormalizedBar:
    step = timedelta(minutes=15 if timeframe == "15m" else 60)
    bar_end_time = BASE_TIME + step * index
    previous_close = Decimal(open_price)
    return NormalizedBar(
        exchange="cn_equity",
        symbol=symbol,
        timeframe=timeframe,
        bar_start_time=bar_end_time - step,
        bar_end_time=bar_end_time,
        ingest_time=bar_end_time + timedelta(minutes=1),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        quote_volume=quote_volume,
        closed=True,
        final=True,
        source_kind="historical",
        market_state=MarketStateSnapshot(
            trade_date=bar_end_time.date(),
            previous_close=previous_close,
            upper_limit_price=(previous_close * Decimal("1.10")).quantize(Decimal("0.01")),
            lower_limit_price=(previous_close * Decimal("0.90")).quantize(Decimal("0.01")),
            trading_phase=TradingPhase.CONTINUOUS_AUCTION,
            suspension_status=SuspensionStatus.ACTIVE,
        ),
    )


def _signal(
    *,
    signal_id: UUID = DEFAULT_SIGNAL_ID,
    trader_run_id: UUID = DEFAULT_TRADER_RUN_ID,
    symbol: str = "600036.SH",
    timeframe: str = "15m",
    target_position: Decimal = Decimal("100"),
    event_time: datetime = BUY_TIME,
) -> Signal:
    return Signal(
        id=signal_id,
        strategy_id="baseline_momentum_v1",
        trader_run_id=trader_run_id,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol=symbol,
        timeframe=timeframe,
        signal_type=SignalType.REBALANCE,
        target_position=target_position,
        event_time=event_time,
        created_at=event_time,
    )


def _order_intent(
    signal: Signal,
    *,
    order_intent_id: UUID = DEFAULT_ORDER_INTENT_ID,
    qty: Decimal = Decimal("100"),
    decision_price: Decimal = Decimal("39.60"),
    created_at: datetime = BUY_TIME,
) -> OrderIntent:
    return OrderIntent(
        id=order_intent_id,
        signal_id=signal.id,
        strategy_id=signal.strategy_id,
        trader_run_id=signal.trader_run_id,
        account_id=signal.account_id,
        exchange=signal.exchange,
        symbol=signal.symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        qty=qty,
        decision_price=decision_price,
        reduce_only=False,
        market_context_json=MARKET_STATE,
        idempotency_key=f"intent:api-market:{order_intent_id}",
        created_at=created_at,
    )


def _order(
    order_intent: OrderIntent,
    *,
    order_id: UUID = DEFAULT_ORDER_ID,
    avg_fill_price: Decimal = Decimal("39.60"),
    submitted_at: datetime = BUY_TIME,
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
        filled_qty=order_intent.qty,
        avg_fill_price=avg_fill_price,
        status=OrderStatus.FILLED,
        submitted_at=submitted_at,
        updated_at=submitted_at,
    )


def _fill(
    order: Order,
    *,
    fill_id: UUID = DEFAULT_FILL_ID,
    qty: Decimal = Decimal("100"),
    price: Decimal = Decimal("39.60"),
    fee: Decimal = Decimal("1.00"),
    fill_time: datetime = BUY_TIME,
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
        qty=qty,
        price=price,
        fee=fee,
        fee_asset="CNY",
        liquidity_type=LiquidityType.TAKER,
        fill_time=fill_time,
        created_at=fill_time,
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
    runtime_state = TraderRuntimeState(
        trader_run_id=str(DEFAULT_TRADER_RUN_ID),
        instance_id="instance-A",
        account_id=settings.account_id,
    )
    runtime_event = bars_15m[-1].to_bar_event()
    runtime_state.record_seen_bar(runtime_event)
    runtime_state.record_strategy_bar(runtime_event)
    control_store.save_runtime_status(
        TraderRuntimeStatusSnapshot(
            account_id=settings.account_id,
            trader_run_id=runtime_state.trader_run_id,
            instance_id=runtime_state.instance_id,
            lifecycle_status="running",
            health_status="alive",
            readiness_status="ready",
            control_state=RiskControlState.NORMAL,
            strategy_enabled=True,
            kill_switch_active=False,
            protection_mode_active=False,
            market_data_fresh=True,
            latest_final_bar_time=runtime_event.event_time,
            current_trading_phase="continuous_auction",
            last_seen_bars={
                stream_key: dict(snapshot)
                for stream_key, snapshot in runtime_state.last_seen_bars_by_stream.items()
            },
            last_strategy_bars={
                stream_key: dict(snapshot)
                for stream_key, snapshot in runtime_state.last_strategy_bars_by_stream.items()
            },
            fencing_token=3,
            last_status_message="bar_observed",
            updated_at=runtime_event.ingest_time,
        )
    )
    service = ApiControlPlaneService(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        market_gateway_factory=lambda: FakeHistoricalBarGateway(
            {
                ("600036.SH", "15m"): bars_15m,
                ("600036.SH", "1h"): bars_1h,
            }
        ),
    )
    app = create_app(settings=settings, control_plane_service=service)

    try:
        with TestClient(app) as client:
            bars_response = client.get("/v1/market/bars", params={"limit": 3})
            runtime_bars_response = client.get(
                "/v1/market/runtime-bars",
                params={"symbol": "600036.SH", "timeframe": "15m"},
            )
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
            "source": "balance_snapshots_plus_portfolio_market_bars",
            "scope": "account_portfolio",
            "anchor_symbol": "600036.SH",
            "valuation_symbols": ["600036.SH"],
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

        assert runtime_bars_response.status_code == 200
        assert runtime_bars_response.json() == {
            "filters": {
                "account_id": settings.account_id,
                "symbol": "600036.SH",
                "timeframe": "15m",
            },
            "source": "trader_runtime_status",
            "trader_run_id": str(DEFAULT_TRADER_RUN_ID),
            "instance_id": "instance-A",
            "lifecycle_status": "running",
            "health_status": "alive",
            "readiness_status": "ready",
            "updated_at": "2026-04-02T10:16:00+08:00",
            "count": {
                "last_seen": 1,
                "last_strategy": 1,
            },
            "available_streams": [
                {
                    "stream_key": "cn_equity:600036.SH:15m",
                    "symbol": "600036.SH",
                    "timeframe": "15m",
                    "exchange": "cn_equity",
                    "last_seen_event_time": "2026-04-02T10:15:00+08:00",
                    "last_strategy_event_time": "2026-04-02T10:15:00+08:00",
                }
            ],
            "last_seen_bars": [
                {
                    "stream_key": "cn_equity:600036.SH:15m",
                    "bar_key": "cn_equity:600036.SH:15m:2026-04-02T10:00:00+08:00",
                    "exchange": "cn_equity",
                    "symbol": "600036.SH",
                    "timeframe": "15m",
                    "bar_start_time": "2026-04-02T10:00:00+08:00",
                    "bar_end_time": "2026-04-02T10:15:00+08:00",
                    "event_time": "2026-04-02T10:15:00+08:00",
                    "ingest_time": "2026-04-02T10:16:00+08:00",
                    "open": 39.45,
                    "high": 39.85,
                    "low": 39.3,
                    "close": 39.8,
                    "volume": 120000.0,
                    "quote_volume": 4740000.0,
                    "trade_count": None,
                    "closed": True,
                    "final": True,
                    "source_kind": "historical",
                    "trade_date": "2026-04-02",
                    "trading_phase": "CONTINUOUS_AUCTION",
                }
            ],
            "last_strategy_bars": [
                {
                    "stream_key": "cn_equity:600036.SH:15m",
                    "bar_key": "cn_equity:600036.SH:15m:2026-04-02T10:00:00+08:00",
                    "exchange": "cn_equity",
                    "symbol": "600036.SH",
                    "timeframe": "15m",
                    "bar_start_time": "2026-04-02T10:00:00+08:00",
                    "bar_end_time": "2026-04-02T10:15:00+08:00",
                    "event_time": "2026-04-02T10:15:00+08:00",
                    "ingest_time": "2026-04-02T10:16:00+08:00",
                    "open": 39.45,
                    "high": 39.85,
                    "low": 39.3,
                    "close": 39.8,
                    "volume": 120000.0,
                    "quote_volume": 4740000.0,
                    "trade_count": None,
                    "closed": True,
                    "final": True,
                    "source_kind": "historical",
                    "trade_date": "2026-04-02",
                    "trading_phase": "CONTINUOUS_AUCTION",
                }
            ],
        }
    finally:
        get_settings.cache_clear()
        os.environ.pop("SIGNALARK_POSTGRES_DSN", None)
        engine.dispose()


def test_api_equity_curve_reconstructs_full_account_portfolio_across_symbols(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv("SIGNALARK_POSTGRES_DSN", database_url)
    from src.config import get_settings

    get_settings.cache_clear()

    settings = Settings(
        postgres_dsn=database_url,
        symbols=["600036.SH", "000001.SZ"],
    )
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory)

    with session_factory.begin() as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        repositories.balance_snapshots.save(
            _balance_snapshot(snapshot_time=BASE_TIME - timedelta(minutes=15), total="100000")
        )

        first_signal = repositories.signals.save(_signal())
        first_intent = repositories.order_intents.save(_order_intent(first_signal))
        first_order = repositories.orders.save(_order(first_intent))
        repositories.fills.save(_fill(first_order))
        repositories.balance_snapshots.save(
            _balance_snapshot(snapshot_time=BUY_TIME, total="96039")
        )

        second_buy_time = BUY_TIME + timedelta(minutes=15)
        second_signal = repositories.signals.save(
            _signal(
                signal_id=UUID("66666666-6666-4666-8666-666666666666"),
                trader_run_id=UUID("77777777-7777-4777-8777-777777777777"),
                symbol="000001.SZ",
                target_position=Decimal("200"),
                event_time=second_buy_time,
            )
        )
        second_intent = repositories.order_intents.save(
            _order_intent(
                second_signal,
                order_intent_id=UUID("88888888-8888-4888-8888-888888888888"),
                qty=Decimal("200"),
                decision_price=Decimal("20.00"),
                created_at=second_buy_time,
            )
        )
        second_order = repositories.orders.save(
            _order(
                second_intent,
                order_id=UUID("99999999-9999-4999-8999-999999999999"),
                avg_fill_price=Decimal("20.00"),
                submitted_at=second_buy_time,
            )
        )
        repositories.fills.save(
            _fill(
                second_order,
                fill_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
                qty=Decimal("200"),
                price=Decimal("20.00"),
                fee=Decimal("1.00"),
                fill_time=second_buy_time,
            )
        )
        repositories.balance_snapshots.save(
            _balance_snapshot(snapshot_time=second_buy_time, total="92038")
        )

    bars_600036 = [
        _bar(index=0, close="39.50"),
        _bar(index=1, close="39.60"),
        _bar(index=2, close="39.80"),
    ]
    bars_000001 = [
        _bar(
            index=0,
            close="19.90",
            symbol="000001.SZ",
            open_price="19.80",
            high="20.10",
            low="19.70",
            volume="180000",
            quote_volume="3600000",
        ),
        _bar(
            index=1,
            close="20.00",
            symbol="000001.SZ",
            open_price="19.90",
            high="20.10",
            low="19.80",
            volume="175000",
            quote_volume="3500000",
        ),
        _bar(
            index=2,
            close="21.00",
            symbol="000001.SZ",
            open_price="20.00",
            high="21.20",
            low="19.95",
            volume="210000",
            quote_volume="4200000",
        ),
    ]
    service = ApiControlPlaneService(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        market_gateway_factory=lambda: FakeHistoricalBarGateway(
            {
                ("600036.SH", "15m"): bars_600036,
                ("000001.SZ", "15m"): bars_000001,
            }
        ),
    )
    from apps.api.main import create_app

    app = create_app(settings=settings, control_plane_service=service)

    try:
        with TestClient(app) as client:
            curve_response = client.get(
                "/v1/portfolio/equity-curve",
                params={"symbol": "600036.SH", "limit": 3},
            )
    finally:
        get_settings.cache_clear()
        os.environ.pop("SIGNALARK_POSTGRES_DSN", None)
        engine.dispose()

    assert curve_response.status_code == 200
    assert curve_response.json() == {
        "account_id": settings.account_id,
        "symbol": "600036.SH",
        "timeframe": "15m",
        "count": 3,
        "source": "balance_snapshots_plus_portfolio_market_bars",
        "scope": "account_portfolio",
        "anchor_symbol": "600036.SH",
        "valuation_symbols": ["600036.SH", "000001.SZ"],
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
                "value": 100218.0,
                "baseline": 100000.0,
            },
        ],
    }
