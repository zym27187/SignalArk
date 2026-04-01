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
    build_order_id_for_intent,
)
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.portfolio import BalanceSnapshot, Position, PositionStatus
from src.domain.risk import RiskControlState
from src.domain.strategy import Signal, SignalType
from src.infra.db import EventLogEntry, RecoveryState
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


def _balance_snapshot(*, snapshot_time: datetime | None = None) -> BalanceSnapshot:
    timestamp = snapshot_time or (BASE_TIME - timedelta(minutes=20))
    return BalanceSnapshot(
        account_id="paper_account_001",
        exchange="cn_equity",
        asset="CNY",
        total=Decimal("100000"),
        available=Decimal("100000"),
        locked=Decimal("0"),
        snapshot_time=timestamp,
        created_at=timestamp,
    )


class RecordingPersistence(OmsPersistencePort):
    def __init__(self) -> None:
        self.operations: list[str] = []
        self.position = _position()
        self.balance_snapshots: list[BalanceSnapshot] = [_balance_snapshot()]
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

    def save_position(self, position: Position) -> Position:
        self.operations.append("save_position")
        self.position = position
        return position

    def save_order_intent(self, order_intent: OrderIntent) -> OrderIntent:
        self.operations.append(f"save_order_intent:{order_intent.status}")
        self.order_intents[order_intent.id] = order_intent
        return order_intent

    def list_recent_active_order_intents(
        self,
        *,
        account_id: str,
        exchange: str,
        symbol: str,
        created_after: datetime,
    ) -> tuple[OrderIntent, ...]:
        self.operations.append("list_recent_active_order_intents")
        active_order_statuses = {OrderStatus.NEW, OrderStatus.ACK, OrderStatus.PARTIALLY_FILLED}
        matches: list[OrderIntent] = []
        for intent in self.order_intents.values():
            if intent.account_id != account_id:
                continue
            if intent.exchange != exchange:
                continue
            if intent.symbol != symbol:
                continue
            if intent.created_at < created_after:
                continue
            if intent.status not in {OrderIntentStatus.NEW, OrderIntentStatus.SUBMITTED}:
                continue

            order = self.orders.get(build_order_id_for_intent(intent.id))
            if order is not None and order.status not in active_order_statuses:
                continue
            matches.append(intent)

        matches.sort(key=lambda intent: intent.created_at, reverse=True)
        return tuple(matches)

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

    def get_fill(self, fill_id: UUID) -> Fill | None:
        self.operations.append("get_fill")
        return self.fills.get(fill_id)

    def save_fill(self, fill: Fill) -> Fill:
        self.operations.append("save_fill")
        self.fills[fill.id] = fill
        return fill

    def get_latest_balance_snapshot(
        self,
        *,
        account_id: str,
        exchange: str,
        asset: str,
    ) -> BalanceSnapshot | None:
        self.operations.append("get_latest_balance_snapshot")
        candidates = [
            snapshot
            for snapshot in self.balance_snapshots
            if snapshot.account_id == account_id
            and snapshot.exchange == exchange
            and snapshot.asset == asset
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda snapshot: snapshot.snapshot_time)

    def save_balance_snapshot(self, balance_snapshot: BalanceSnapshot) -> BalanceSnapshot:
        self.operations.append("save_balance_snapshot")
        self.balance_snapshots.append(balance_snapshot)
        return balance_snapshot

    def load_recovery_state(
        self,
        *,
        account_id: str,
        trader_run_id: UUID | None = None,
        event_limit: int = 100,
    ) -> RecoveryState:
        open_orders = tuple(
            order
            for order in self.orders.values()
            if order.status in {OrderStatus.NEW, OrderStatus.ACK, OrderStatus.PARTIALLY_FILLED}
        )
        open_positions = ()
        if self.position is not None and self.position.status is PositionStatus.OPEN:
            open_positions = (self.position,)
        latest_balance_snapshots = ()
        latest_balance = self.get_latest_balance_snapshot(
            account_id=account_id,
            exchange="cn_equity",
            asset="CNY",
        )
        if latest_balance is not None:
            latest_balance_snapshots = (latest_balance,)
        recent_event_logs = tuple(self.event_logs[-event_limit:])
        return RecoveryState(
            open_orders=open_orders,
            open_positions=open_positions,
            latest_balance_snapshots=latest_balance_snapshots,
            recent_event_logs=recent_event_logs,
        )


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
    assert "save_position" in persistence.operations
    assert "save_balance_snapshot" in persistence.operations
    assert persistence.position.qty == Decimal("350")
    assert persistence.position.sellable_qty == Decimal("250")
    assert persistence.position.realized_pnl == Decimal("-1.2245")
    latest_balance = persistence.get_latest_balance_snapshot(
        account_id="paper_account_001",
        exchange="cn_equity",
        asset="CNY",
    )
    assert latest_balance is not None
    assert latest_balance.available == Decimal("96048.7755")
    event_types = [event.event_type for event in persistence.event_logs]
    assert "execution.order_updated" in event_types
    assert "execution.fill_recorded" in event_types
    assert "portfolio.position_updated" in event_types
    assert "portfolio.balance_updated" in event_types


@pytest.mark.asyncio
async def test_trader_oms_service_releases_sellable_qty_before_sizing_on_new_trade_date() -> None:
    persistence = RecordingPersistence()
    persistence.position = Position(
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        qty=Decimal("300"),
        sellable_qty=Decimal("0"),
        avg_entry_price=Decimal("39.20"),
        mark_price=Decimal("39.20"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.OPEN,
        updated_at=BASE_TIME - timedelta(days=1),
    )
    gateway = RecordingGateway(persistence.operations)
    service = TraderOmsService(persistence, execution_gateway=gateway)
    reduction_signal = _signal().model_copy(update={"target_position": Decimal("0")})
    next_day_market_state = MARKET_STATE.model_copy(update={"trade_date": BASE_TIME.date()})

    result = await service.submit_signal(
        signal=reduction_signal,
        symbol_rule=SYMBOL_RULE,
        decision_price=Decimal("39.50"),
        market_context=next_day_market_state,
        received_at=BASE_TIME + timedelta(seconds=2),
    )

    assert result is not None
    assert result.plan.qty == Decimal("300")
    assert result.plan.side.value == "SELL"
    assert persistence.position.sellable_qty == Decimal("300")
    event_types = [event.event_type for event in persistence.event_logs]
    assert "portfolio.sellable_qty_released" in event_types


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


@pytest.mark.asyncio
async def test_trader_oms_service_rejects_stale_market_data_before_persisting_order_intent() -> (
    None
):
    persistence = RecordingPersistence()
    gateway = RecordingGateway(persistence.operations)
    service = TraderOmsService(persistence, execution_gateway=gateway)

    result = await service.submit_signal(
        signal=_signal(),
        symbol_rule=SYMBOL_RULE,
        decision_price=Decimal("39.50"),
        market_context=MARKET_STATE,
        received_at=BASE_TIME + timedelta(minutes=31),
    )

    assert result is None
    assert not persistence.order_intents
    assert not persistence.orders
    assert not gateway.calls
    assert persistence.event_logs[-1].event_type == "oms.risk_rejected"
    assert (
        persistence.event_logs[-1].payload_json["risk_result"]["reason_code"] == "MARKET_DATA_STALE"
    )


@pytest.mark.asyncio
async def test_trader_oms_service_kill_switch_rejects_opening_buy_orders() -> None:
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
    gateway = RecordingGateway(persistence.operations)
    service = TraderOmsService(persistence, execution_gateway=gateway)

    result = await service.submit_signal(
        signal=_signal().model_copy(update={"target_position": Decimal("300")}),
        symbol_rule=SYMBOL_RULE,
        decision_price=Decimal("39.50"),
        market_context=MARKET_STATE,
        control_state=RiskControlState.KILL_SWITCH,
        received_at=BASE_TIME + timedelta(seconds=2),
    )

    assert result is None
    assert not persistence.order_intents
    assert not persistence.orders
    assert not gateway.calls
    assert persistence.event_logs[-1].event_type == "oms.risk_rejected"
    assert (
        persistence.event_logs[-1].payload_json["risk_result"]["reason_code"]
        == "KILL_SWITCH_REDUCE_ONLY"
    )


@pytest.mark.asyncio
async def test_trader_oms_service_kill_switch_allows_reducing_sell_orders() -> None:
    persistence = RecordingPersistence()
    persistence.position = Position(
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        qty=Decimal("300"),
        sellable_qty=Decimal("300"),
        avg_entry_price=Decimal("39.20"),
        mark_price=Decimal("39.50"),
        unrealized_pnl=Decimal("90"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.OPEN,
        updated_at=BASE_TIME - timedelta(minutes=15),
    )
    gateway = RecordingGateway(persistence.operations)
    service = TraderOmsService(persistence, execution_gateway=gateway)

    result = await service.submit_signal(
        signal=_signal().model_copy(
            update={"signal_type": SignalType.EXIT, "target_position": Decimal("0")}
        ),
        symbol_rule=SYMBOL_RULE,
        decision_price=Decimal("39.50"),
        market_context=MARKET_STATE,
        control_state=RiskControlState.KILL_SWITCH,
        received_at=BASE_TIME + timedelta(seconds=2),
    )

    assert result is not None
    assert result.plan.side.value == "SELL"
    assert result.plan.qty == Decimal("300")
    assert len(gateway.calls) == 1
    assert persistence.event_logs[0].event_type == "oms.order_intent_persisted"


@pytest.mark.asyncio
async def test_trader_oms_service_rejects_near_duplicate_active_order_intents() -> None:
    persistence = RecordingPersistence()
    gateway = RecordingGateway(persistence.operations)
    service = TraderOmsService(persistence, execution_gateway=gateway)
    first_signal = _signal().model_copy(update={"id": UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")})
    first_result = await service.submit_signal(
        signal=first_signal,
        symbol_rule=SYMBOL_RULE,
        decision_price=Decimal("39.50"),
        market_context=MARKET_STATE,
        received_at=BASE_TIME + timedelta(seconds=2),
    )

    assert first_result is not None

    duplicate_signal = _signal().model_copy(
        update={
            "id": UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
            "created_at": BASE_TIME + timedelta(seconds=3),
        }
    )
    duplicate_result = await service.submit_signal(
        signal=duplicate_signal,
        symbol_rule=SYMBOL_RULE,
        decision_price=Decimal("39.50"),
        market_context=MARKET_STATE,
        received_at=BASE_TIME + timedelta(seconds=4),
    )

    assert duplicate_result is None
    assert len(persistence.order_intents) == 1
    assert len(persistence.orders) == 1
    assert not gateway.calls[1:]
    assert persistence.event_logs[-1].event_type == "oms.risk_rejected"
    assert (
        persistence.event_logs[-1].payload_json["risk_result"]["reason_code"]
        == "DUPLICATE_ORDER_INTENT"
    )
