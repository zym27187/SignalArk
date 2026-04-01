from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from src.config.settings import AshareSymbolRule
from src.domain.execution import OrderType, build_signal_order_intent_plan
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.portfolio import Position, PositionStatus
from src.domain.risk import (
    PreTradeRiskContext,
    PreTradeRiskGate,
    PreTradeRiskPolicy,
    RiskControlState,
    resolve_risk_control_state,
)
from src.domain.strategy import Signal, SignalType

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 1, 10, 0, tzinfo=SHANGHAI)
BASE_SIGNAL_ID = UUID("11111111-1111-4111-8111-111111111111")
TRADER_RUN_ID = UUID("22222222-2222-4222-8222-222222222222")
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


def _signal(
    *,
    signal_id: UUID = BASE_SIGNAL_ID,
    target_position: Decimal = Decimal("400"),
    signal_type: SignalType = SignalType.REBALANCE,
    event_time: datetime = BASE_TIME,
    created_at: datetime | None = None,
) -> Signal:
    return Signal(
        id=signal_id,
        strategy_id="baseline_momentum_v1",
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        signal_type=signal_type,
        target_position=target_position,
        event_time=event_time,
        created_at=created_at or (event_time + timedelta(seconds=1)),
    )


def _position(
    *,
    qty: Decimal,
    sellable_qty: Decimal,
    symbol: str = "600036.SH",
    mark_price: Decimal | None = Decimal("39.50"),
) -> Position:
    return Position(
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol=symbol,
        qty=qty,
        sellable_qty=sellable_qty,
        avg_entry_price=Decimal("39.20") if qty > 0 else None,
        mark_price=mark_price if qty > 0 else None,
        unrealized_pnl=Decimal("30") if qty > 0 else Decimal("0"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.OPEN if qty > 0 else PositionStatus.CLOSED,
        updated_at=BASE_TIME - timedelta(minutes=15),
    )


def _plan(
    *,
    signal: Signal,
    current_position: Position | None,
    decision_price: Decimal = Decimal("39.50"),
    market_context: MarketStateSnapshot = MARKET_STATE,
    order_type: OrderType = OrderType.MARKET,
    price: Decimal | None = None,
):
    return build_signal_order_intent_plan(
        signal=signal,
        symbol_rule=SYMBOL_RULE,
        current_position=current_position,
        decision_price=decision_price,
        market_context=market_context,
        order_type=order_type,
        price=price,
    )


def _context(
    *,
    signal: Signal | None = None,
    current_position: Position | None = None,
    decision_price: Decimal | None = Decimal("39.50"),
    market_context: MarketStateSnapshot | None = MARKET_STATE,
    order_type: OrderType = OrderType.MARKET,
    price: Decimal | None = None,
    control_state: RiskControlState = RiskControlState.NORMAL,
    recent_active_order_intents=(),
    open_positions=(),
    policy: PreTradeRiskPolicy | None = None,
):
    resolved_signal = signal or _signal()
    plan = None
    if market_context is not None and decision_price is not None and decision_price > 0:
        plan = _plan(
            signal=resolved_signal,
            current_position=current_position,
            decision_price=decision_price,
            market_context=market_context,
            order_type=order_type,
            price=price,
        )
    resolved_open_positions = open_positions
    if not resolved_open_positions and current_position is not None and current_position.qty > 0:
        resolved_open_positions = (current_position,)
    return (
        PreTradeRiskGate(policy=policy),
        PreTradeRiskContext(
            signal=resolved_signal,
            decision_price=decision_price,
            received_at=resolved_signal.created_at,
            symbol_rule=SYMBOL_RULE,
            market_context=market_context,
            current_position=current_position,
            open_positions=resolved_open_positions,
            recent_active_order_intents=recent_active_order_intents,
            plan=plan,
            order_type=order_type,
            price=price,
            control_state=control_state,
        ),
    )


def test_pretrade_risk_rejects_stale_market_data() -> None:
    signal = _signal(created_at=BASE_TIME + timedelta(minutes=31))
    gate, context = _context(
        signal=signal,
        current_position=_position(qty=Decimal("250"), sellable_qty=Decimal("250")),
    )

    result = gate.evaluate(context)

    assert result.allowed is False
    assert result.reason_code == "MARKET_DATA_STALE"


def test_resolve_risk_control_state_honors_fixed_priority() -> None:
    assert (
        resolve_risk_control_state(
            strategy_enabled=True,
            kill_switch_active=False,
            protection_mode_active=False,
        )
        is RiskControlState.NORMAL
    )
    assert (
        resolve_risk_control_state(
            strategy_enabled=False,
            kill_switch_active=False,
            protection_mode_active=False,
        )
        is RiskControlState.STRATEGY_PAUSED
    )
    assert (
        resolve_risk_control_state(
            strategy_enabled=False,
            kill_switch_active=True,
            protection_mode_active=False,
        )
        is RiskControlState.KILL_SWITCH
    )
    assert (
        resolve_risk_control_state(
            strategy_enabled=True,
            kill_switch_active=True,
            protection_mode_active=True,
        )
        is RiskControlState.PROTECTION_MODE
    )


def test_pretrade_risk_rejects_limit_without_market_state() -> None:
    signal = _signal()
    gate, context = _context(
        signal=signal,
        current_position=_position(qty=Decimal("250"), sellable_qty=Decimal("250")),
        market_context=None,
        order_type=OrderType.LIMIT,
        price=Decimal("39.50"),
    )

    result = gate.evaluate(context)

    assert result.allowed is False
    assert result.reason_code == "LIMIT_REQUIRES_MARKET_STATE"


@pytest.mark.parametrize(
    ("market_state", "expected_reason_code"),
    [
        (
            MARKET_STATE.model_copy(update={"suspension_status": SuspensionStatus.SUSPENDED}),
            "SECURITY_SUSPENDED",
        ),
        (
            MARKET_STATE.model_copy(update={"trading_phase": TradingPhase.PRE_OPEN}),
            "TRADING_SESSION_UNSUPPORTED",
        ),
    ],
)
def test_pretrade_risk_rejects_invalid_market_contracts(
    market_state: MarketStateSnapshot,
    expected_reason_code: str,
) -> None:
    gate, context = _context(
        current_position=_position(qty=Decimal("250"), sellable_qty=Decimal("250")),
        market_context=market_state,
    )

    result = gate.evaluate(context)

    assert result.allowed is False
    assert result.reason_code == expected_reason_code


def test_pretrade_risk_rejects_partial_odd_lot_sell() -> None:
    signal = _signal(target_position=Decimal("20"), signal_type=SignalType.REDUCE)
    odd_lot_position = _position(qty=Decimal("50"), sellable_qty=Decimal("50"))
    gate, context = _context(signal=signal, current_position=odd_lot_position)

    result = gate.evaluate(context)

    assert result.allowed is False
    assert result.reason_code == "ODD_LOT_SELL_RULE_VIOLATION"


def test_pretrade_risk_enforces_kill_switch_reduce_only_boundary() -> None:
    buy_gate, buy_context = _context(
        signal=_signal(target_position=Decimal("300")),
        current_position=_position(qty=Decimal("0"), sellable_qty=Decimal("0")),
        control_state=RiskControlState.KILL_SWITCH,
    )
    sell_gate, sell_context = _context(
        signal=_signal(target_position=Decimal("0"), signal_type=SignalType.EXIT),
        current_position=_position(qty=Decimal("300"), sellable_qty=Decimal("300")),
        control_state=RiskControlState.KILL_SWITCH,
    )

    buy_result = buy_gate.evaluate(buy_context)
    sell_result = sell_gate.evaluate(sell_context)

    assert buy_result.allowed is False
    assert buy_result.reason_code == "KILL_SWITCH_REDUCE_ONLY"
    assert sell_result.allowed is True


def test_pretrade_risk_enforces_protection_mode_reduce_only_boundary() -> None:
    buy_gate, buy_context = _context(
        signal=_signal(target_position=Decimal("300")),
        current_position=_position(qty=Decimal("0"), sellable_qty=Decimal("0")),
        control_state=RiskControlState.PROTECTION_MODE,
    )
    sell_gate, sell_context = _context(
        signal=_signal(target_position=Decimal("0"), signal_type=SignalType.EXIT),
        current_position=_position(qty=Decimal("300"), sellable_qty=Decimal("300")),
        control_state=RiskControlState.PROTECTION_MODE,
    )

    buy_result = buy_gate.evaluate(buy_context)
    sell_result = sell_gate.evaluate(sell_context)

    assert buy_result.allowed is False
    assert buy_result.reason_code == "PROTECTION_MODE_REDUCE_ONLY"
    assert sell_result.allowed is True


def test_pretrade_risk_rejects_duplicate_active_intent_but_ignores_same_signal_retry() -> None:
    current_position = _position(qty=Decimal("250"), sellable_qty=Decimal("250"))
    new_signal = _signal(signal_id=UUID("33333333-3333-4333-8333-333333333333"))
    existing_signal = _signal(
        signal_id=UUID("44444444-4444-4444-8444-444444444444"),
        created_at=BASE_TIME + timedelta(seconds=2),
    )
    existing_plan = _plan(signal=existing_signal, current_position=current_position)
    existing_intent = existing_plan.to_order_intent(created_at=BASE_TIME + timedelta(seconds=3))

    gate, context = _context(
        signal=new_signal,
        current_position=current_position,
        recent_active_order_intents=(existing_intent,),
    )
    duplicate_result = gate.evaluate(context)

    same_signal_gate, same_signal_context = _context(
        signal=existing_signal,
        current_position=current_position,
        recent_active_order_intents=(existing_intent,),
    )
    retry_result = same_signal_gate.evaluate(same_signal_context)

    assert duplicate_result.allowed is False
    assert duplicate_result.reason_code == "DUPLICATE_ORDER_INTENT"
    assert retry_result.allowed is True


@pytest.mark.parametrize(
    ("price", "expected_reason_code"),
    [
        (Decimal("39.505"), "PRICE_TICK_VIOLATION"),
        (Decimal("44.00"), "PRICE_LIMIT_EXCEEDED"),
    ],
)
def test_pretrade_risk_rejects_invalid_limit_price_contracts(
    price: Decimal,
    expected_reason_code: str,
) -> None:
    gate, context = _context(
        current_position=_position(qty=Decimal("250"), sellable_qty=Decimal("250")),
        order_type=OrderType.LIMIT,
        price=price,
    )

    result = gate.evaluate(context)

    assert result.allowed is False
    assert result.reason_code == expected_reason_code


def test_pretrade_risk_rejects_min_order_notional() -> None:
    policy = PreTradeRiskPolicy(
        max_single_symbol_notional_cny=Decimal("200000"),
        max_total_open_notional_cny=Decimal("500000"),
        min_order_notional_cny=Decimal("5000"),
        market_stale_threshold_seconds=120,
        duplicate_window_seconds=60,
    )
    gate, context = _context(
        signal=_signal(target_position=Decimal("100")),
        current_position=_position(qty=Decimal("0"), sellable_qty=Decimal("0")),
        policy=policy,
    )

    result = gate.evaluate(context)

    assert result.allowed is False
    assert result.reason_code == "MIN_ORDER_NOTIONAL_NOT_MET"


def test_pretrade_risk_rejects_single_symbol_and_total_open_notional_limits() -> None:
    single_symbol_policy = PreTradeRiskPolicy(
        max_single_symbol_notional_cny=Decimal("10000"),
        max_total_open_notional_cny=Decimal("500000"),
        min_order_notional_cny=Decimal("1000"),
        market_stale_threshold_seconds=120,
        duplicate_window_seconds=60,
    )
    gate, context = _context(
        current_position=_position(qty=Decimal("250"), sellable_qty=Decimal("250")),
        policy=single_symbol_policy,
    )
    single_symbol_result = gate.evaluate(context)

    account_policy = PreTradeRiskPolicy(
        max_single_symbol_notional_cny=Decimal("500000"),
        max_total_open_notional_cny=Decimal("40000"),
        min_order_notional_cny=Decimal("1000"),
        market_stale_threshold_seconds=120,
        duplicate_window_seconds=60,
    )
    other_position = _position(
        qty=Decimal("400"),
        sellable_qty=Decimal("400"),
        symbol="000001.SZ",
        mark_price=Decimal("100.00"),
    )
    total_gate, total_context = _context(
        current_position=_position(qty=Decimal("250"), sellable_qty=Decimal("250")),
        open_positions=(
            _position(qty=Decimal("250"), sellable_qty=Decimal("250")),
            other_position,
        ),
        policy=account_policy,
    )
    total_result = total_gate.evaluate(total_context)

    assert single_symbol_result.allowed is False
    assert single_symbol_result.reason_code == "MAX_POSITION_EXCEEDED"
    assert total_result.allowed is False
    assert total_result.reason_code == "MAX_OPEN_NOTIONAL_EXCEEDED"
