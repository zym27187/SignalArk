from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from src.config.settings import AshareSymbolRule
from src.domain.execution import OrderSide, build_signal_order_intent_plan
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.portfolio import Position, PositionStatus
from src.domain.strategy import Signal, SignalType

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 1, 10, 0, tzinfo=SHANGHAI)
TRADER_RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
SYMBOL_RULE = AshareSymbolRule(
    lot_size=Decimal("100"),
    qty_step=Decimal("100"),
    price_tick=Decimal("0.01"),
    min_qty=Decimal("100"),
    allow_odd_lot_sell=True,
    t_plus_one_sell=True,
    price_limit_pct=Decimal("0.10"),
)
MARKET_STATE = MarketStateSnapshot(
    trade_date=BASE_TIME.date(),
    previous_close=Decimal("39.47"),
    upper_limit_price=Decimal("43.42"),
    lower_limit_price=Decimal("35.52"),
    trading_phase=TradingPhase.CONTINUOUS_AUCTION,
    suspension_status=SuspensionStatus.ACTIVE,
)


def _signal(*, target_position: Decimal, signal_type: SignalType = SignalType.REBALANCE) -> Signal:
    return Signal(
        id=UUID("22222222-2222-4222-8222-222222222222"),
        strategy_id="baseline_momentum_v1",
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        signal_type=signal_type,
        target_position=target_position,
        event_time=BASE_TIME,
        created_at=BASE_TIME + timedelta(seconds=1),
    )


def _position(*, qty: Decimal, sellable_qty: Decimal) -> Position:
    return Position(
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        qty=qty,
        sellable_qty=sellable_qty,
        avg_entry_price=Decimal("39.20") if qty > 0 else None,
        mark_price=Decimal("39.50") if qty > 0 else None,
        unrealized_pnl=Decimal("30") if qty > 0 else Decimal("0"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.OPEN if qty > 0 else PositionStatus.CLOSED,
        updated_at=BASE_TIME - timedelta(minutes=15),
    )


def test_signal_target_position_maps_to_normalized_buy_qty() -> None:
    plan = build_signal_order_intent_plan(
        signal=_signal(target_position=Decimal("420")),
        symbol_rule=SYMBOL_RULE,
        current_position=_position(qty=Decimal("250"), sellable_qty=Decimal("250")),
        decision_price=Decimal("39.50"),
        market_context=MARKET_STATE,
    )

    assert plan.actionable is True
    assert plan.side is OrderSide.BUY
    assert plan.raw_delta_qty == Decimal("170")
    assert plan.qty == Decimal("100")
    assert plan.reduce_only is False


def test_signal_target_position_caps_sell_qty_by_sellable_inventory() -> None:
    plan = build_signal_order_intent_plan(
        signal=_signal(target_position=Decimal("0"), signal_type=SignalType.EXIT),
        symbol_rule=SYMBOL_RULE,
        current_position=_position(qty=Decimal("500"), sellable_qty=Decimal("300")),
        decision_price=Decimal("39.50"),
        market_context=MARKET_STATE,
    )

    assert plan.actionable is True
    assert plan.side is OrderSide.SELL
    assert plan.qty == Decimal("300")
    assert plan.current_sellable_qty == Decimal("300")
    assert plan.reduce_only is True
    assert plan.odd_lot_sell is False


def test_signal_target_position_allows_one_shot_odd_lot_sell() -> None:
    plan = build_signal_order_intent_plan(
        signal=_signal(target_position=Decimal("0"), signal_type=SignalType.EXIT),
        symbol_rule=SYMBOL_RULE,
        current_position=_position(qty=Decimal("50"), sellable_qty=Decimal("50")),
        decision_price=Decimal("39.50"),
        market_context=MARKET_STATE,
    )

    assert plan.actionable is True
    assert plan.side is OrderSide.SELL
    assert plan.qty == Decimal("50")
    assert plan.reduce_only is True
    assert plan.odd_lot_sell is True


def test_signal_target_position_returns_non_actionable_when_target_already_met() -> None:
    plan = build_signal_order_intent_plan(
        signal=_signal(target_position=Decimal("300")),
        symbol_rule=SYMBOL_RULE,
        current_position=_position(qty=Decimal("300"), sellable_qty=Decimal("300")),
        decision_price=Decimal("39.50"),
        market_context=MARKET_STATE,
    )

    assert plan.actionable is False
    assert plan.qty == Decimal("0")
    assert plan.skip_reason == "target_position_already_satisfied"
