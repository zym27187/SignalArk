from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from src.config.settings import PaperCostModel
from src.domain.execution import (
    Fill,
    Order,
    OrderIntent,
    OrderIntentStatus,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from src.domain.portfolio import BalanceSnapshot, Position, PositionStatus
from src.domain.reconciliation import PaperReconciliationFacts, reconcile_paper_state

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 1, 14, 0, tzinfo=SHANGHAI)
TRADER_RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
SIGNAL_ID = UUID("22222222-2222-4222-8222-222222222222")
ORDER_INTENT_ID = UUID("33333333-3333-4333-8333-333333333333")
ORDER_ID = UUID("44444444-4444-4444-8444-444444444444")
FILL_ID = UUID("55555555-5555-4555-8555-555555555555")
COST_MODEL = PaperCostModel(
    commission=Decimal("0.0003"),
    transfer_fee=Decimal("0.00001"),
    stamp_duty_sell=Decimal("0.0005"),
)


def _order_intent() -> OrderIntent:
    return OrderIntent(
        id=ORDER_INTENT_ID,
        signal_id=SIGNAL_ID,
        strategy_id="baseline_momentum_v1",
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        qty=Decimal("300"),
        decision_price=Decimal("10.00"),
        idempotency_key="intent:reconciliation:001",
        status=OrderIntentStatus.SUBMITTED,
        created_at=BASE_TIME - timedelta(minutes=2),
    )


def _order() -> Order:
    return Order(
        id=ORDER_ID,
        order_intent_id=ORDER_INTENT_ID,
        trader_run_id=TRADER_RUN_ID,
        exchange_order_id="paper-order-001",
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        qty=Decimal("300"),
        filled_qty=Decimal("300"),
        avg_fill_price=Decimal("10.00"),
        status=OrderStatus.FILLED,
        submitted_at=BASE_TIME - timedelta(minutes=2),
        updated_at=BASE_TIME - timedelta(minutes=1),
    )


def _fill(*, fee: Decimal = Decimal("0.9300")) -> Fill:
    return Fill(
        id=FILL_ID,
        order_id=ORDER_ID,
        trader_run_id=TRADER_RUN_ID,
        exchange_fill_id="paper-fill-001",
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        side=OrderSide.BUY,
        qty=Decimal("300"),
        price=Decimal("10.00"),
        fee=fee,
        fee_asset="CNY",
        fill_time=BASE_TIME - timedelta(minutes=1),
        created_at=BASE_TIME - timedelta(minutes=1),
    )


def _baseline_balance() -> BalanceSnapshot:
    snapshot_time = BASE_TIME - timedelta(minutes=5)
    return BalanceSnapshot(
        account_id="paper_account_001",
        exchange="cn_equity",
        asset="CNY",
        total=Decimal("100000"),
        available=Decimal("100000"),
        locked=Decimal("0"),
        snapshot_time=snapshot_time,
        created_at=snapshot_time,
    )


def _latest_balance(*, total: Decimal = Decimal("96999.0700")) -> BalanceSnapshot:
    snapshot_time = BASE_TIME - timedelta(minutes=1)
    return BalanceSnapshot(
        account_id="paper_account_001",
        exchange="cn_equity",
        asset="CNY",
        total=total,
        available=total,
        locked=Decimal("0"),
        snapshot_time=snapshot_time,
        created_at=snapshot_time,
    )


def _position(*, sellable_qty: Decimal = Decimal("0")) -> Position:
    return Position(
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        qty=Decimal("300"),
        sellable_qty=sellable_qty,
        avg_entry_price=Decimal("10.00"),
        mark_price=Decimal("10.00"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("-0.9300"),
        status=PositionStatus.OPEN,
        updated_at=BASE_TIME - timedelta(minutes=1),
    )


def _facts(
    *,
    fill_fee: Decimal = Decimal("0.9300"),
    sellable_qty: Decimal = Decimal("0"),
    latest_balance_total: Decimal = Decimal("96999.0700"),
    effective_trade_date: date | None = None,
) -> PaperReconciliationFacts:
    return PaperReconciliationFacts(
        account_id="paper_account_001",
        exchange="cn_equity",
        effective_trade_date=effective_trade_date or BASE_TIME.date(),
        trigger="unit_test",
        order_intents=(_order_intent(),),
        orders=(_order(),),
        fills=(_fill(fee=fill_fee),),
        positions=(_position(sellable_qty=sellable_qty),),
        balance_snapshots=(_baseline_balance(), _latest_balance(total=latest_balance_total)),
    )


def test_reconcile_paper_state_accepts_consistent_paper_facts() -> None:
    result = reconcile_paper_state(
        facts=_facts(),
        cost_model=COST_MODEL,
        checked_at=BASE_TIME,
    )

    assert result.has_drift is False
    assert result.summary.issue_count == 0
    assert result.summary.total_commission == Decimal("0.9000")
    assert result.summary.total_transfer_fee == Decimal("0.0300")
    assert result.summary.total_stamp_duty == Decimal("0")
    assert result.summary.total_fee == Decimal("0.9300")
    assert result.summary.total_net_cash_flow == Decimal("-3000.9300")


def test_reconcile_paper_state_detects_fill_fee_drift_and_stops_fill_replay() -> None:
    result = reconcile_paper_state(
        facts=_facts(
            fill_fee=Decimal("0.5000"),
        ),
        cost_model=COST_MODEL,
        checked_at=BASE_TIME,
    )

    issue_codes = {issue.code for issue in result.issues}

    assert result.has_drift is True
    assert "FILL_FEE_DRIFT" in issue_codes
    assert "FILL_LEDGER_REPLAY_FAILED" in issue_codes
    assert "POSITION_UNBACKED_BY_FILLS" in issue_codes


def test_reconcile_paper_state_detects_position_and_balance_state_drift() -> None:
    result = reconcile_paper_state(
        facts=_facts(
            sellable_qty=Decimal("300"),
            latest_balance_total=Decimal("100000"),
        ),
        cost_model=COST_MODEL,
        checked_at=BASE_TIME,
    )

    issue_codes = {issue.code for issue in result.issues}

    assert result.has_drift is True
    assert "POSITION_STATE_DRIFT" in issue_codes
    assert "BALANCE_STATE_DRIFT" in issue_codes
