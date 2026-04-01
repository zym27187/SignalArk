from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from src.config.settings import PaperCostModel
from src.domain.execution import (
    OrderIntent,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
    apply_order_update,
    create_order_from_intent,
)
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.infra.exchanges import PaperExecutionAdapter, PaperExecutionScenario, PaperFillSlice

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 1, 10, 45, tzinfo=SHANGHAI)
TRADER_RUN_ID = UUID("acacacac-acac-4cac-8cac-acacacacacac")
SIGNAL_ID = UUID("bdbdbdbd-bdbd-4dbd-8dbd-bdbdbdbdbdbd")
ORDER_INTENT_ID = UUID("cececece-cece-4ece-8ece-cececececece")
MARKET_STATE = MarketStateSnapshot(
    trade_date=BASE_TIME.date(),
    previous_close=Decimal("39.47"),
    upper_limit_price=Decimal("43.42"),
    lower_limit_price=Decimal("35.52"),
    trading_phase=TradingPhase.CONTINUOUS_AUCTION,
    suspension_status=SuspensionStatus.ACTIVE,
)


def _paper_cost_model() -> PaperCostModel:
    return PaperCostModel(
        commission=Decimal("0.0003"),
        transfer_fee=Decimal("0.00001"),
        stamp_duty_sell=Decimal("0.0005"),
    )


def _order_intent(
    *,
    qty: Decimal,
    order_type: OrderType = OrderType.MARKET,
    decision_price: Decimal = Decimal("39.50"),
    price: Decimal | None = None,
    market_state: MarketStateSnapshot = MARKET_STATE,
) -> OrderIntent:
    return OrderIntent(
        id=ORDER_INTENT_ID,
        signal_id=SIGNAL_ID,
        strategy_id="baseline_momentum_v1",
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        side=OrderSide.BUY,
        order_type=order_type,
        time_in_force=TimeInForce.DAY,
        qty=qty,
        price=price,
        decision_price=decision_price,
        market_context_json=market_state,
        idempotency_key=f"paper:{order_type.value}:{qty}",
        created_at=BASE_TIME,
    )


@pytest.mark.asyncio
async def test_paper_execution_adapter_generates_ack_fill_and_a_share_cost_fields() -> None:
    adapter = PaperExecutionAdapter(
        cost_model=_paper_cost_model(),
        clock=lambda: BASE_TIME + timedelta(seconds=1),
    )
    order_intent = _order_intent(qty=Decimal("100"))
    order = create_order_from_intent(order_intent, submitted_at=BASE_TIME)

    report = await adapter.submit_order(order, order_intent)

    assert [update.status for update in report.order_updates] == [
        OrderStatus.ACK,
        OrderStatus.FILLED,
    ]
    assert len(report.fill_events) == 1
    fill_event = report.fill_events[0]
    assert fill_event.fill.fee == Decimal("1.2245")
    assert fill_event.cost_breakdown.commission == Decimal("1.1850")
    assert fill_event.cost_breakdown.transfer_fee == Decimal("0.0395")
    assert fill_event.cost_breakdown.stamp_duty == Decimal("0.0000")
    assert fill_event.cost_breakdown.total_fee == Decimal("1.2245")
    assert fill_event.cost_breakdown.net_cash_flow == Decimal("-3951.2245")


@pytest.mark.asyncio
async def test_paper_execution_adapter_rejects_market_orders_outside_continuous_auction() -> None:
    adapter = PaperExecutionAdapter(
        cost_model=_paper_cost_model(),
        clock=lambda: BASE_TIME + timedelta(seconds=1),
    )
    pre_open_state = MARKET_STATE.model_copy(update={"trading_phase": TradingPhase.PRE_OPEN})
    order_intent = _order_intent(qty=Decimal("100"), market_state=pre_open_state)
    order = create_order_from_intent(order_intent, submitted_at=BASE_TIME)

    report = await adapter.submit_order(order, order_intent)

    assert len(report.fill_events) == 0
    assert len(report.order_updates) == 1
    reject_update = report.order_updates[0]
    assert reject_update.status is OrderStatus.REJECTED
    assert reject_update.error_code == "UNSUPPORTED_TRADING_PHASE"


@pytest.mark.asyncio
async def test_paper_execution_adapter_supports_partial_then_cancel() -> None:
    adapter = PaperExecutionAdapter(
        cost_model=_paper_cost_model(),
        clock=lambda: BASE_TIME + timedelta(seconds=1),
        scenario_resolver=lambda _order, _intent: PaperExecutionScenario(
            fill_slices=(PaperFillSlice(qty=Decimal("100"), price=Decimal("39.50")),),
        ),
    )
    order_intent = _order_intent(qty=Decimal("300"))
    order = create_order_from_intent(order_intent, submitted_at=BASE_TIME)

    submit_report = await adapter.submit_order(order, order_intent)

    assert [update.status for update in submit_report.order_updates] == [
        OrderStatus.ACK,
        OrderStatus.PARTIALLY_FILLED,
    ]
    partially_filled_order = order
    for update in submit_report.order_updates:
        partially_filled_order = apply_order_update(partially_filled_order, update)

    cancel_report = await adapter.cancel_order(partially_filled_order)

    assert len(cancel_report.order_updates) == 1
    cancel_update = cancel_report.order_updates[0]
    assert cancel_update.status is OrderStatus.CANCELED
    assert cancel_update.filled_qty == Decimal("100")
    assert cancel_update.avg_fill_price == Decimal("39.50")


@pytest.mark.asyncio
async def test_paper_execution_adapter_explicitly_rejects_resting_limit_orders() -> None:
    adapter = PaperExecutionAdapter(
        cost_model=_paper_cost_model(),
        clock=lambda: BASE_TIME + timedelta(seconds=1),
    )
    order_intent = _order_intent(
        qty=Decimal("100"),
        order_type=OrderType.LIMIT,
        decision_price=Decimal("39.50"),
        price=Decimal("39.00"),
    )
    order = create_order_from_intent(order_intent, submitted_at=BASE_TIME)

    report = await adapter.submit_order(order, order_intent)

    assert len(report.fill_events) == 0
    assert len(report.order_updates) == 1
    reject_update = report.order_updates[0]
    assert reject_update.status is OrderStatus.REJECTED
    assert reject_update.error_code == "RESTING_LIMIT_NOT_SUPPORTED"
