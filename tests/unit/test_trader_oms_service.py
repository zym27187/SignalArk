from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from apps.trader.oms import OmsPersistencePort, TraderOmsService
from src.config.settings import AshareSymbolRule
from src.domain.execution import Order, OrderIntent, OrderIntentStatus, OrderStatus
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.portfolio import Position, PositionStatus
from src.domain.strategy import Signal, SignalType
from src.infra.db import EventLogEntry

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


class RecordingPersistence(OmsPersistencePort):
    def __init__(self) -> None:
        self.operations: list[str] = []
        self.position = _position()
        self.signals: dict[UUID, Signal] = {}
        self.order_intents: dict[UUID, OrderIntent] = {}
        self.orders: dict[UUID, Order] = {}
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


class RecordingGateway:
    def __init__(self, operations: list[str]) -> None:
        self.operations = operations
        self.calls: list[tuple[Order, OrderIntent]] = []

    async def submit_order(self, order: Order, order_intent: OrderIntent) -> None:
        self.operations.append("gateway.submit_order")
        self.calls.append((order, order_intent))


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
