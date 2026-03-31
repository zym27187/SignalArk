from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from src.domain.events import BarEvent
from src.domain.execution import Fill, LiquidityType, OrderIntent, OrderSide, OrderType, TimeInForce
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.portfolio import BalanceSnapshot, Position, PositionStatus
from src.domain.strategy import Signal, SignalType

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 3, 31, 12, 0, tzinfo=SHANGHAI)
TRADER_RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
SIGNAL_ID = UUID("22222222-2222-4222-8222-222222222222")
ORDER_ID = UUID("33333333-3333-4333-8333-333333333333")
MARKET_STATE = MarketStateSnapshot(
    trade_date=BASE_TIME.date(),
    previous_close=Decimal("39.47"),
    upper_limit_price=Decimal("43.42"),
    lower_limit_price=Decimal("35.52"),
    trading_phase=TradingPhase.CONTINUOUS_AUCTION,
    suspension_status=SuspensionStatus.ACTIVE,
)


def test_bar_event_exposes_stable_window_key_and_actionable_finality() -> None:
    bar = BarEvent(
        exchange="CN_EQUITY",
        symbol="600036.sh",
        timeframe="1H",
        bar_start_time=BASE_TIME,
        bar_end_time=BASE_TIME + timedelta(hours=1),
        event_time=BASE_TIME + timedelta(hours=1),
        ingest_time=BASE_TIME + timedelta(hours=1, seconds=2),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("99"),
        close=Decimal("104"),
        volume=Decimal("12.5"),
        quote_volume=Decimal("1290"),
        trade_count=42,
        closed=True,
        final=True,
        market_state=MARKET_STATE,
    )

    assert bar.exchange == "cn_equity"
    assert bar.symbol == "600036.SH"
    assert bar.timeframe == "1h"
    assert bar.bar_key == "cn_equity:600036.SH:1h:2026-03-31T12:00:00+08:00"
    assert bar.time_window == (BASE_TIME, BASE_TIME + timedelta(hours=1))
    assert bar.actionable is True
    assert bar.decision_price == Decimal("104")
    assert bar.market_state is not None
    assert bar.market_state.previous_close == Decimal("39.47")


def test_bar_event_requires_final_bars_to_be_closed() -> None:
    with pytest.raises(ValueError, match="final bars must also be closed"):
        BarEvent(
            exchange="cn_equity",
            symbol="600036.SH",
            timeframe="1m",
            bar_start_time=BASE_TIME,
            bar_end_time=BASE_TIME + timedelta(minutes=1),
            event_time=BASE_TIME + timedelta(minutes=1),
            ingest_time=BASE_TIME + timedelta(minutes=1),
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("99"),
            close=Decimal("99"),
            volume=Decimal("1"),
            closed=False,
            final=True,
        )


def test_signal_and_order_intent_keep_target_position_separate_from_order_qty() -> None:
    signal = Signal(
        id=SIGNAL_ID,
        strategy_id="baseline_momentum_v1",
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="1h",
        signal_type=SignalType.REBALANCE,
        target_position=Decimal("1200"),
        confidence=Decimal("0.78"),
        reason_summary="rebalance to desired inventory",
        event_time=BASE_TIME + timedelta(hours=1),
        created_at=BASE_TIME + timedelta(hours=1, seconds=1),
    )

    intent = OrderIntent(
        signal_id=signal.id,
        strategy_id=signal.strategy_id,
        trader_run_id=signal.trader_run_id,
        account_id=signal.account_id,
        exchange=signal.exchange,
        symbol=signal.symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        qty=Decimal("300"),
        decision_price=Decimal("39.42"),
        idempotency_key="signalark:intent:rebalance-001",
        created_at=BASE_TIME + timedelta(hours=1, seconds=2),
    )

    assert signal.target_position == Decimal("1200")
    assert intent.qty == Decimal("300")
    assert intent.qty != signal.target_position
    assert intent.price is None
    assert intent.decision_price == Decimal("39.42")
    assert intent.time_in_force is TimeInForce.DAY
    assert intent.notional == Decimal("11826.00")


def test_limit_order_intent_defaults_decision_price_to_limit_price() -> None:
    intent = OrderIntent(
        signal_id=SIGNAL_ID,
        strategy_id="baseline_momentum_v1",
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="000001.SZ",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        qty=Decimal("500"),
        price=Decimal("11.25"),
        reduce_only=True,
        market_context_json=MARKET_STATE,
        idempotency_key="signalark:intent:reduce-001",
        created_at=BASE_TIME + timedelta(hours=1, seconds=2),
    )

    assert intent.decision_price == Decimal("11.25")
    assert intent.market_state is not None
    assert intent.market_state.trade_date == BASE_TIME.date()


def test_limit_order_intent_requires_market_context_in_a_share_v1() -> None:
    with pytest.raises(ValueError, match="LIMIT orders require market_context_json"):
        OrderIntent(
            signal_id=SIGNAL_ID,
            strategy_id="baseline_momentum_v1",
            trader_run_id=TRADER_RUN_ID,
            account_id="paper_account_001",
            exchange="cn_equity",
            symbol="000001.SZ",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            qty=Decimal("500"),
            price=Decimal("11.25"),
            reduce_only=True,
            idempotency_key="signalark:intent:reduce-002",
            created_at=BASE_TIME + timedelta(hours=1, seconds=2),
        )


def test_order_intent_rejects_non_day_time_in_force_in_v1() -> None:
    with pytest.raises(ValidationError, match="Input should be 'DAY'"):
        OrderIntent(
            signal_id=SIGNAL_ID,
            strategy_id="baseline_momentum_v1",
            trader_run_id=TRADER_RUN_ID,
            account_id="paper_account_001",
            exchange="cn_equity",
            symbol="600036.SH",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            time_in_force="IOC",
            qty=Decimal("100"),
            decision_price=Decimal("39.42"),
            idempotency_key="signalark:intent:invalid-tif",
            created_at=BASE_TIME + timedelta(hours=1, seconds=2),
        )


def test_fill_position_and_balance_snapshot_validate_core_fact_fields() -> None:
    fill = Fill(
        id=ORDER_ID,
        order_id=ORDER_ID,
        trader_run_id=TRADER_RUN_ID,
        exchange_fill_id="paper-fill-001",
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        side=OrderSide.BUY,
        qty=Decimal("300"),
        price=Decimal("39.42"),
        fee=Decimal("0.10"),
        fee_asset="CNY",
        liquidity_type=LiquidityType.TAKER,
        fill_time=BASE_TIME + timedelta(hours=1, seconds=3),
        created_at=BASE_TIME + timedelta(hours=1, seconds=4),
    )
    position = Position(
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        qty=Decimal("300"),
        sellable_qty=Decimal("0"),
        avg_entry_price=Decimal("39.42"),
        mark_price=Decimal("39.50"),
        unrealized_pnl=Decimal("24"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.OPEN,
        updated_at=BASE_TIME + timedelta(hours=1, seconds=5),
    )
    balance = BalanceSnapshot(
        account_id="paper_account_001",
        exchange="cn_equity",
        asset="cny",
        total=Decimal("100000"),
        available=Decimal("90000"),
        locked=Decimal("10000"),
        snapshot_time=BASE_TIME + timedelta(hours=1, seconds=6),
        created_at=BASE_TIME + timedelta(hours=1, seconds=7),
    )

    assert fill.notional == Decimal("11826.00")
    assert position.status is PositionStatus.OPEN
    assert position.qty == Decimal("300")
    assert position.sellable_qty == Decimal("0")
    assert balance.asset == "CNY"
    assert balance.available + balance.locked == balance.total


def test_position_rejects_sellable_qty_greater_than_qty() -> None:
    with pytest.raises(ValueError, match="sellable_qty cannot exceed qty"):
        Position(
            account_id="paper_account_001",
            exchange="cn_equity",
            symbol="600036.SH",
            qty=Decimal("100"),
            sellable_qty=Decimal("200"),
            avg_entry_price=Decimal("39.42"),
            status=PositionStatus.OPEN,
            updated_at=BASE_TIME + timedelta(hours=1, seconds=5),
        )
