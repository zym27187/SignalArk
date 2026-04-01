from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from apps.trader.control_plane import (
    SubmissionLeaseGuard,
    TraderControlSnapshot,
    TraderLeaseSnapshot,
)
from apps.trader.oms import OmsPersistencePort, TraderOmsService, build_default_trader_oms_service
from src.config import Settings
from src.config.settings import AshareSymbolRule, PaperCostModel
from src.domain.execution import (
    ExecutionReport,
    Fill,
    Order,
    OrderIntent,
    OrderIntentStatus,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
    build_order_id_for_intent,
    create_order_from_intent,
)
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.portfolio import BalanceSnapshot, Position, PositionStatus
from src.domain.risk import RiskControlState
from src.domain.strategy import Signal, SignalType
from src.infra.db import (
    Base,
    EventLogEntry,
    RecoveryState,
    create_database_engine,
    create_session_factory,
)
from src.infra.exchanges import PaperExecutionAdapter, PaperExecutionScenario, PaperFillSlice
from src.infra.observability import AlertRouter, RecordingAlertSink, SignalArkObservability

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


def _observability(sink: RecordingAlertSink) -> SignalArkObservability:
    return SignalArkObservability(
        service="tests",
        alert_router=AlertRouter((sink,), clock=lambda: BASE_TIME),
        clock=lambda: BASE_TIME,
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

    def get_order_intent(self, order_intent_id: UUID) -> OrderIntent | None:
        self.operations.append("get_order_intent")
        return self.order_intents.get(order_intent_id)

    def list_active_orders(self, *, account_id: str) -> tuple[Order, ...]:
        self.operations.append("list_active_orders")
        return tuple(
            order
            for order in self.orders.values()
            if order.account_id == account_id
            and order.status in {OrderStatus.NEW, OrderStatus.ACK, OrderStatus.PARTIALLY_FILLED}
        )

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


class FakeControlStore:
    def __init__(
        self,
        *,
        control_snapshot: TraderControlSnapshot | None = None,
        lease_valid: bool = True,
    ) -> None:
        self.control_snapshot = control_snapshot or TraderControlSnapshot(
            account_id="paper_account_001"
        )
        self.lease_valid = lease_valid
        self.protection_mode_requests: list[tuple[str, bool]] = []

    def get_control_snapshot(self, account_id: str) -> TraderControlSnapshot:
        assert account_id == self.control_snapshot.account_id
        return self.control_snapshot

    def validate_submission_lease(
        self,
        *,
        account_id: str,
        instance_id: str,
        fencing_token: int,
        now: datetime | None = None,
    ):
        return type(
            "LeaseResult",
            (),
            {
                "accepted": self.lease_valid,
                "message": "lease_valid_for_submission" if self.lease_valid else "lease_not_held",
                "snapshot": TraderLeaseSnapshot(
                    account_id=account_id,
                    owner_instance_id=("other-instance" if not self.lease_valid else instance_id),
                    lease_expires_at=now,
                    last_heartbeat_at=now,
                    fencing_token=(fencing_token + 1 if not self.lease_valid else fencing_token),
                ),
            },
        )()

    def set_protection_mode(
        self,
        *,
        account_id: str,
        active: bool,
    ) -> TraderControlSnapshot:
        self.protection_mode_requests.append((account_id, active))
        self.control_snapshot = TraderControlSnapshot(
            account_id=account_id,
            strategy_enabled=self.control_snapshot.strategy_enabled,
            kill_switch_active=self.control_snapshot.kill_switch_active,
            protection_mode_active=active,
            cancel_all_token=self.control_snapshot.cancel_all_token,
            last_cancel_all_at=self.control_snapshot.last_cancel_all_at,
            updated_at=BASE_TIME,
        )
        return self.control_snapshot


class FailingOrderIntentPersistence(RecordingPersistence):
    def save_order_intent(self, order_intent: OrderIntent) -> OrderIntent:
        raise RuntimeError("order_intent_write_failed")


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


@pytest.mark.asyncio
async def test_trader_oms_service_rejects_submission_when_submission_guard_is_invalid() -> None:
    persistence = RecordingPersistence()
    gateway = RecordingGateway(persistence.operations)
    sink = RecordingAlertSink()
    service = TraderOmsService(
        persistence,
        execution_gateway=gateway,
        control_store=FakeControlStore(lease_valid=False),
        observability=_observability(sink),
    )

    result = await service.submit_signal(
        signal=_signal(),
        symbol_rule=SYMBOL_RULE,
        decision_price=Decimal("39.50"),
        market_context=MARKET_STATE,
        submission_guard=SubmissionLeaseGuard(
            account_id="paper_account_001",
            instance_id="instance-A",
            fencing_token=7,
        ),
        received_at=BASE_TIME + timedelta(seconds=2),
    )

    assert result is None
    assert not persistence.order_intents
    assert not persistence.orders
    assert not gateway.calls
    assert persistence.event_logs[-1].event_type == "oms.risk_rejected"
    assert persistence.event_logs[-1].payload_json["risk_result"]["reason_code"] == "LEASE_NOT_HELD"
    assert [event.event_name for event in sink.events] == ["oms.risk_rejected"]
    assert sink.events[0].reason_code == "LEASE_NOT_HELD"


@pytest.mark.asyncio
async def test_trader_oms_service_alerts_after_repeated_risk_rejections() -> None:
    persistence = RecordingPersistence()
    sink = RecordingAlertSink()
    service = TraderOmsService(
        persistence,
        execution_gateway=RecordingGateway(persistence.operations),
        observability=_observability(sink),
    )

    for offset_seconds in (31, 32, 33):
        result = await service.submit_signal(
            signal=_signal().model_copy(
                update={"created_at": BASE_TIME + timedelta(seconds=offset_seconds)}
            ),
            symbol_rule=SYMBOL_RULE,
            decision_price=Decimal("39.50"),
            market_context=MARKET_STATE,
            received_at=BASE_TIME + timedelta(minutes=offset_seconds),
        )

        assert result is None

    assert [event.event_name for event in sink.events] == ["oms.risk_rejected"]
    assert sink.events[0].reason_code == "MARKET_DATA_STALE"


@pytest.mark.asyncio
async def test_trader_oms_service_alerts_on_order_intent_write_failure() -> None:
    persistence = FailingOrderIntentPersistence()
    sink = RecordingAlertSink()
    service = TraderOmsService(
        persistence,
        execution_gateway=RecordingGateway(persistence.operations),
        observability=_observability(sink),
    )

    with pytest.raises(RuntimeError, match="order_intent_write_failed"):
        await service.submit_signal(
            signal=_signal(),
            symbol_rule=SYMBOL_RULE,
            decision_price=Decimal("39.50"),
            market_context=MARKET_STATE,
            received_at=BASE_TIME + timedelta(seconds=2),
        )

    assert [event.event_name for event in sink.events] == ["db.order_intent_write_failed"]
    assert sink.events[0].reason_code == "ORDER_INTENT_WRITE_FAILED"


@pytest.mark.asyncio
async def test_trader_oms_service_enters_protection_mode_after_critical_write_failure() -> None:
    persistence = FailingOrderIntentPersistence()
    sink = RecordingAlertSink()
    control_store = FakeControlStore()
    service = TraderOmsService(
        persistence,
        execution_gateway=RecordingGateway(persistence.operations),
        control_store=control_store,
        observability=_observability(sink),
    )

    with pytest.raises(RuntimeError, match="order_intent_write_failed"):
        await service.submit_signal(
            signal=_signal(),
            symbol_rule=SYMBOL_RULE,
            decision_price=Decimal("39.50"),
            market_context=MARKET_STATE,
            received_at=BASE_TIME + timedelta(seconds=2),
        )

    assert control_store.protection_mode_requests == [("paper_account_001", True)]
    assert [event.event_name for event in sink.events] == [
        "control.protection_mode_requested",
        "db.order_intent_write_failed",
    ]
    assert sink.events[0].reason_code == "ORDER_INTENT_WRITE_FAILED"


def test_build_default_trader_oms_service_uses_settings_backed_risk_policy(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'settings_backed_oms.sqlite3'}"
    engine = create_database_engine(database_url)
    Base.metadata.create_all(bind=engine)
    try:
        session_factory = create_session_factory(engine)
        settings = Settings(
            postgres_dsn=database_url,
            max_single_symbol_notional_cny=Decimal("123456"),
            max_total_open_notional_cny=Decimal("654321"),
            min_order_notional_cny=Decimal("4321"),
            market_stale_threshold_seconds=77,
        )

        service = build_default_trader_oms_service(
            settings=settings,
            session_factory=session_factory,
        )

        policy = service._risk_gate.policy
        assert policy.max_single_symbol_notional_cny == Decimal("123456")
        assert policy.max_total_open_notional_cny == Decimal("654321")
        assert policy.min_order_notional_cny == Decimal("4321")
        assert policy.market_stale_threshold_seconds == 77
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_trader_oms_service_cancel_all_preserves_reduce_only_orders_in_kill_switch() -> None:
    persistence = RecordingPersistence()
    gateway = PaperExecutionAdapter(cost_model=_paper_cost_model())
    service = TraderOmsService(persistence, execution_gateway=gateway)
    buy_signal = _signal().model_copy(update={"id": UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")})
    sell_signal = _signal().model_copy(update={"id": UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")})
    buy_intent = OrderIntent(
        signal_id=buy_signal.id,
        strategy_id=buy_signal.strategy_id,
        trader_run_id=buy_signal.trader_run_id,
        account_id=buy_signal.account_id,
        exchange=buy_signal.exchange,
        symbol=buy_signal.symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        qty=Decimal("100"),
        decision_price=Decimal("39.50"),
        idempotency_key="test-buy-intent",
        created_at=BASE_TIME + timedelta(seconds=1),
    )
    reduce_only_intent = OrderIntent(
        signal_id=sell_signal.id,
        strategy_id=sell_signal.strategy_id,
        trader_run_id=sell_signal.trader_run_id,
        account_id=sell_signal.account_id,
        exchange=sell_signal.exchange,
        symbol=sell_signal.symbol,
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        qty=Decimal("100"),
        decision_price=Decimal("39.50"),
        reduce_only=True,
        idempotency_key="test-reduce-only-intent",
        created_at=BASE_TIME + timedelta(seconds=2),
    )
    persistence.signals[buy_signal.id] = buy_signal
    persistence.signals[sell_signal.id] = sell_signal
    persistence.order_intents[buy_intent.id] = buy_intent.model_copy(
        update={"status": OrderIntentStatus.SUBMITTED}
    )
    persistence.order_intents[reduce_only_intent.id] = reduce_only_intent.model_copy(
        update={"status": OrderIntentStatus.SUBMITTED}
    )
    persistence.orders[build_order_id_for_intent(buy_intent.id)] = create_order_from_intent(
        persistence.order_intents[buy_intent.id],
        submitted_at=BASE_TIME + timedelta(seconds=3),
    )
    persistence.orders[build_order_id_for_intent(reduce_only_intent.id)] = create_order_from_intent(
        persistence.order_intents[reduce_only_intent.id],
        submitted_at=BASE_TIME + timedelta(seconds=4),
    )

    result = await service.cancel_all_orders(
        account_id="paper_account_001",
        control_state=RiskControlState.KILL_SWITCH,
        received_at=BASE_TIME + timedelta(seconds=10),
    )

    assert result.requested_order_count == 2
    assert result.cancelled_order_count == 1
    assert result.skipped_order_count == 1
    assert (
        persistence.orders[build_order_id_for_intent(buy_intent.id)].status is OrderStatus.CANCELED
    )
    assert (
        persistence.orders[build_order_id_for_intent(reduce_only_intent.id)].status
        is OrderStatus.NEW
    )
