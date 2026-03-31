from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from src.domain.events import BarEvent
from src.domain.execution import Fill, LiquidityType, OrderIntent, OrderSide, OrderType, TimeInForce
from src.domain.portfolio import BalanceSnapshot, Position, PositionStatus
from src.domain.strategy import Signal, SignalType

BASE_TIME = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
TRADER_RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
SIGNAL_ID = UUID("22222222-2222-4222-8222-222222222222")
ORDER_ID = UUID("33333333-3333-4333-8333-333333333333")


def test_bar_event_exposes_stable_window_key_and_actionable_finality() -> None:
    bar = BarEvent(
        exchange="BINANCE",
        symbol="btcusdt",
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
    )

    assert bar.exchange == "binance"
    assert bar.symbol == "BTCUSDT"
    assert bar.timeframe == "1h"
    assert bar.bar_key == "binance:BTCUSDT:1h:2026-03-31T12:00:00+00:00"
    assert bar.time_window == (BASE_TIME, BASE_TIME + timedelta(hours=1))
    assert bar.actionable is True
    assert bar.decision_price == Decimal("104")


def test_bar_event_requires_final_bars_to_be_closed() -> None:
    with pytest.raises(ValueError, match="final bars must also be closed"):
        BarEvent(
            exchange="binance",
            symbol="BTCUSDT",
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
        exchange="binance",
        symbol="BTCUSDT",
        timeframe="1h",
        signal_type=SignalType.REBALANCE,
        target_position=Decimal("1.2500"),
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
        time_in_force=TimeInForce.IOC,
        qty=Decimal("0.3000"),
        decision_price=Decimal("104"),
        idempotency_key="signalark:intent:rebalance-001",
        created_at=BASE_TIME + timedelta(hours=1, seconds=2),
    )

    assert signal.target_position == Decimal("1.2500")
    assert intent.qty == Decimal("0.3000")
    assert intent.qty != signal.target_position
    assert intent.price is None
    assert intent.decision_price == Decimal("104")
    assert intent.notional == Decimal("31.2000")


def test_limit_order_intent_defaults_decision_price_to_limit_price() -> None:
    intent = OrderIntent(
        signal_id=SIGNAL_ID,
        strategy_id="baseline_momentum_v1",
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="binance",
        symbol="ETHUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        qty=Decimal("0.5"),
        price=Decimal("2500"),
        reduce_only=True,
        idempotency_key="signalark:intent:reduce-001",
        created_at=BASE_TIME + timedelta(hours=1, seconds=2),
    )

    assert intent.decision_price == Decimal("2500")


def test_fill_position_and_balance_snapshot_validate_core_fact_fields() -> None:
    fill = Fill(
        id=ORDER_ID,
        order_id=ORDER_ID,
        trader_run_id=TRADER_RUN_ID,
        exchange_fill_id="paper-fill-001",
        account_id="paper_account_001",
        exchange="binance",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        qty=Decimal("0.25"),
        price=Decimal("103"),
        fee=Decimal("0.10"),
        fee_asset="USDT",
        liquidity_type=LiquidityType.TAKER,
        fill_time=BASE_TIME + timedelta(hours=1, seconds=3),
        created_at=BASE_TIME + timedelta(hours=1, seconds=4),
    )
    position = Position(
        account_id="paper_account_001",
        exchange="binance",
        symbol="BTCUSDT",
        qty=Decimal("0.25"),
        avg_entry_price=Decimal("103"),
        mark_price=Decimal("104"),
        unrealized_pnl=Decimal("0.25"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.OPEN,
        updated_at=BASE_TIME + timedelta(hours=1, seconds=5),
    )
    balance = BalanceSnapshot(
        account_id="paper_account_001",
        exchange="binance",
        asset="usdt",
        total=Decimal("1000"),
        available=Decimal("900"),
        locked=Decimal("100"),
        snapshot_time=BASE_TIME + timedelta(hours=1, seconds=6),
        created_at=BASE_TIME + timedelta(hours=1, seconds=7),
    )

    assert fill.notional == Decimal("25.75")
    assert position.status is PositionStatus.OPEN
    assert position.qty == Decimal("0.25")
    assert balance.asset == "USDT"
    assert balance.available + balance.locked == balance.total
