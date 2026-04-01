from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from apps.trader.oms import OmsPersistencePort, TraderOmsService
from src.config.settings import AshareSymbolRule, PaperCostModel
from src.domain.execution import (
    ExecutionReport,
    Fill,
    Order,
    OrderIntent,
    OrderIntentStatus,
    OrderStatus,
)
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.portfolio import Position, PositionStatus
from src.domain.strategy import Signal, SignalType
from src.infra.db import EventLogEntry
from src.infra.exchanges import PaperExecutionAdapter, PaperExecutionScenario, PaperFillSlice

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 1, 10, 30, tzinfo=SHANGHAI)
TRADER_RUN_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
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


def _signal() -> Signal:
    return Signal(
        id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        strategy_id="baseline_momentum_v1",
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        signal_type=SignalType.REBALANCE,
        target_position=Decimal("400"),
        event_time=BASE_TIME,
        created_at=BASE_TIME + timedelta(seconds=1),
    )


def _position() -> Position:
    return Position(
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        qty=Decimal("250"),
        sellable_qty=Decimal("250"),
        avg_entry_price=Decimal("39.20"),
        mark_price=Decimal("39.50"),
        unrealized_pnl=Decimal("75"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.OPEN,
        updated_at=BASE_TIME - timedelta(minutes=15),
    )


def _paper_cost_model() -> PaperCostModel:
    return PaperCostModel(
        commission=Decimal("0.0003"),
        transfer_fee=Decimal("0.00001"),
        stamp_duty_sell=Decimal("0.0005"),
    )


class RecordingPersistence(OmsPersistencePort):
    def __init__(self) -> None:
        self.operations: list[str] = []
        self.position = _position()
        self.signals: dict[UUID, Signal] = {}
        self.order_intents: dict[UUID, OrderIntent] = {}
        self.orders: dict[UUID, Order] = {}
        self.fills: dict[UUID, Fill] = {}
        self.event_logs: list[EventLogEntry] = []

    def save_signal(self, signal: Signal) -> Signal:
        self.operations.append("save_signal")
        self.signals[signal.id] = signal
        return signal

    def get_position(self, *, account_id: str, exchange: str, symbol: str) -> Position | None:
        self.operations.append("get_position")
        return self.position

    def save_order_intent(self, order_intent: OrderIntent) -> OrderIntent:
        self.operations.append(f"save_order_intent:{order_intent.status}")
        self.order_intents[order_intent.id] = order_intent
        return order_intent

    def save_order(self, order: Order) -> Order:
        self.operations.append(f"save_order:{order.status}")
        self.orders[order.id] = order
        return order

    def get_order(self, order_id: UUID) -> Order | None:
        self.operations.append("get_order")
        return self.orders.get(order_id)

    def save_event_log(self, event_log: EventLogEntry) -> EventLogEntry:
        self.operations.append(f"save_event_log:{event_log.event_type}")
        self.event_logs.append(event_log)
        return event_log

    def save_fill(self, fill: Fill) -> Fill:
        self.operations.append("save_fill")
        self.fills[fill.id] = fill
        return fill


class RecordingGateway:
    def __init__(self, operations: list[str]) -> None:
        self.operations = operations
        self.calls: list[tuple[Order, OrderIntent]] = []

    async def submit_order(self, order: Order, order_intent: OrderIntent) -> ExecutionReport:
        self.operations.append("gateway.submit_order")
        self.calls.append((order, order_intent))
        return ExecutionReport()

    async def cancel_order(self, order: Order) -> ExecutionReport:
        self.operations.append("gateway.cancel_order")
        return ExecutionReport()


@pytest.mark.asyncio
async def test_trader_oms_service_persists_order_intent_before_execution_handoff() -> None:
    persistence = RecordingPersistence()
    gateway = RecordingGateway(persistence.operations)
    service = TraderOmsService(persistence, execution_gateway=gateway)

    result = await service.submit_signal(
        signal=_signal(),
        symbol_rule=SYMBOL_RULE,
        decision_price=Decimal("39.50"),
        market_context=MARKET_STATE,
        received_at=BASE_TIME + timedelta(seconds=2),
    )

    assert result is not None
    assert result.order.status is OrderStatus.NEW
    assert result.order_intent.status is OrderIntentStatus.SUBMITTED
    assert len(gateway.calls) == 1
    assert persistence.operations.index("save_order_intent:NEW") < persistence.operations.index(
        "gateway.submit_order"
    )
    assert persistence.operations.index("save_order:NEW") < persistence.operations.index(
        "gateway.submit_order"
    )
    assert persistence.operations[-2] == "save_order_intent:SUBMITTED"
    assert persistence.operations[-1] == "save_event_log:oms.execution_submission_requested"


@pytest.mark.asyncio
async def test_trader_oms_service_applies_paper_execution_updates_and_fill_events() -> None:
    persistence = RecordingPersistence()
    gateway = PaperExecutionAdapter(
        cost_model=_paper_cost_model(),
        clock=lambda: BASE_TIME + timedelta(seconds=3),
    )
    service = TraderOmsService(persistence, execution_gateway=gateway)

    result = await service.submit_signal(
        signal=_signal(),
        symbol_rule=SYMBOL_RULE,
        decision_price=Decimal("39.50"),
        market_context=MARKET_STATE,
        received_at=BASE_TIME + timedelta(seconds=2),
    )

    assert result is not None
    assert result.order.status is OrderStatus.FILLED
    assert result.order.filled_qty == Decimal("100")
    assert result.order.avg_fill_price == Decimal("39.50")
    assert len(persistence.fills) == 1
    assert "save_order:ACK" in persistence.operations
    assert "save_order:FILLED" in persistence.operations
    assert "save_fill" in persistence.operations
    event_types = [event.event_type for event in persistence.event_logs]
    assert "execution.order_updated" in event_types
    assert "execution.fill_recorded" in event_types


@pytest.mark.asyncio
async def test_trader_oms_service_can_cancel_a_partially_filled_paper_order() -> None:
    persistence = RecordingPersistence()
    persistence.position = Position(
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        qty=Decimal("0"),
        sellable_qty=Decimal("0"),
        avg_entry_price=None,
        mark_price=None,
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.CLOSED,
        updated_at=BASE_TIME - timedelta(minutes=15),
    )
    gateway = PaperExecutionAdapter(
        cost_model=_paper_cost_model(),
        clock=lambda: BASE_TIME + timedelta(seconds=3),
        scenario_resolver=lambda _order, _intent: PaperExecutionScenario(
            fill_slices=(PaperFillSlice(qty=Decimal("100"), price=Decimal("39.50")),),
        ),
    )
    service = TraderOmsService(persistence, execution_gateway=gateway)

    submission = await service.submit_signal(
        signal=_signal(),
        symbol_rule=SYMBOL_RULE,
        decision_price=Decimal("39.50"),
        market_context=MARKET_STATE,
        received_at=BASE_TIME + timedelta(seconds=2),
    )

    assert submission is not None
    assert submission.order.status is OrderStatus.PARTIALLY_FILLED

    canceled_order = await service.cancel_order(
        order_id=submission.order.id,
        received_at=BASE_TIME + timedelta(seconds=10),
    )

    assert canceled_order is not None
    assert canceled_order.status is OrderStatus.CANCELED
    assert canceled_order.filled_qty == Decimal("100")
    assert canceled_order.avg_fill_price == Decimal("39.50")
    event_types = [event.event_type for event in persistence.event_logs]
    assert "oms.execution_cancel_requested" in event_types
