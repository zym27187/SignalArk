from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from apps.api.control_plane import ApiControlPlaneService
from apps.trader.control_plane import TraderControlPlaneStore, TraderControlRuntime
from apps.trader.oms import build_default_trader_oms_service
from apps.trader.reconciliation import (
    SessionFactoryBackedReconciliationStore,
    TraderReconciliationRuntime,
)
from apps.trader.runtime import TraderRuntimeState
from apps.trader.service import OmsSignalRiskRouter, TraderPipelinePorts, TraderService
from fastapi.testclient import TestClient
from sqlalchemy import select
from src.config.settings import Settings
from src.domain.events import BarEvent
from src.domain.execution import (
    Fill,
    LiquidityType,
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
from src.domain.strategy import BaselineMomentumStrategy, Signal, SignalType
from src.infra.db import (
    Base,
    EventLogRecord,
    FillRecord,
    OrderRecord,
    SqlAlchemyRepositories,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from src.infra.exchanges import PaperExecutionAdapter
from src.infra.observability import AlertRouter, RecordingAlertSink, SignalArkObservability

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 1, 14, 0, tzinfo=SHANGHAI)
PREVIOUS_DAY = BASE_TIME - timedelta(days=1)
FILLED_RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
MARKET_STATE = MarketStateSnapshot(
    trade_date=BASE_TIME.date(),
    previous_close=Decimal("39.47"),
    upper_limit_price=Decimal("43.42"),
    lower_limit_price=Decimal("35.52"),
    trading_phase=TradingPhase.CONTINUOUS_AUCTION,
    suspension_status=SuspensionStatus.ACTIVE,
)


@dataclass
class MutableClock:
    value: datetime

    def now(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


class QueueEventSource:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[object] = asyncio.Queue()
        self._sentinel = object()
        self._finished = False

    async def publish(self, event: object) -> None:
        await self._queue.put(event)

    async def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        await self._queue.put(self._sentinel)

    def events(self) -> AsyncIterator[object]:
        async def _iterator() -> AsyncIterator[object]:
            while True:
                item = await self._queue.get()
                if item is self._sentinel:
                    return
                yield item

        return _iterator()

    async def aclose(self) -> None:
        await self.finish()


@dataclass
class E2EHarness:
    settings: Settings
    clock: MutableClock
    engine: object
    session_factory: object
    control_store: TraderControlPlaneStore
    control_runtime: TraderControlRuntime
    source: QueueEventSource
    trader: TraderService
    alert_sink: RecordingAlertSink
    observability: SignalArkObservability

    def create_client(self) -> TestClient:
        os.environ["SIGNALARK_POSTGRES_DSN"] = self.settings.postgres_dsn
        from apps.api.main import create_app

        service = ApiControlPlaneService(
            settings=self.settings,
            session_factory=self.session_factory,
            control_store=self.control_store,
            observability=self.observability,
        )
        return TestClient(create_app(settings=self.settings, control_plane_service=service))

    def dispose(self) -> None:
        self.engine.dispose()


def _database_url(tmp_path: Path, name: str) -> str:
    return f"sqlite+pysqlite:///{tmp_path / name}"


def _bar_event(
    *,
    event_time: datetime,
    close: Decimal,
    market_state: MarketStateSnapshot | None = MARKET_STATE,
) -> BarEvent:
    return BarEvent(
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        bar_start_time=event_time - timedelta(minutes=15),
        bar_end_time=event_time,
        event_time=event_time,
        ingest_time=event_time + timedelta(seconds=2),
        open=Decimal("39.40"),
        high=max(close, Decimal("39.55")),
        low=min(close, Decimal("39.38")),
        close=close,
        volume=Decimal("1000"),
        closed=True,
        final=True,
        source_kind="realtime",
        market_state=market_state,
    )


def _balance_snapshot(snapshot_time: datetime) -> BalanceSnapshot:
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


def _signal(
    *,
    signal_id: UUID,
    target_position: Decimal,
    event_time: datetime,
    signal_type: SignalType = SignalType.REBALANCE,
) -> Signal:
    return Signal(
        id=signal_id,
        strategy_id="baseline_momentum_v1",
        trader_run_id=FILLED_RUN_ID,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        signal_type=signal_type,
        target_position=target_position,
        event_time=event_time,
        created_at=event_time + timedelta(seconds=1),
        reason_summary="e2e reconciliation seed",
    )


def _active_order_intent(
    *,
    signal: Signal,
    order_intent_id: UUID,
    side: OrderSide,
    qty: Decimal,
    reduce_only: bool,
    created_at: datetime,
) -> OrderIntent:
    return OrderIntent(
        id=order_intent_id,
        signal_id=signal.id,
        strategy_id=signal.strategy_id,
        trader_run_id=signal.trader_run_id,
        account_id=signal.account_id,
        exchange=signal.exchange,
        symbol=signal.symbol,
        side=side,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        qty=qty,
        decision_price=Decimal("10.00")
        if created_at.date() == PREVIOUS_DAY.date()
        else Decimal("39.50"),
        reduce_only=reduce_only,
        market_context_json=MARKET_STATE,
        idempotency_key=f"intent:{order_intent_id}",
        status=OrderIntentStatus.SUBMITTED,
        created_at=created_at,
    )


def _build_harness(
    tmp_path: Path,
    *,
    database_name: str,
    with_reconciliation: bool = False,
) -> E2EHarness:
    database_url = _database_url(tmp_path, database_name)
    settings = Settings(postgres_dsn=database_url)
    clock = MutableClock(BASE_TIME)
    engine = create_database_engine(database_url)
    Base.metadata.create_all(bind=engine)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory, clock=clock.now)
    control_store.ensure_schema()
    alert_sink = RecordingAlertSink()
    observability = SignalArkObservability(
        service="tests",
        alert_router=AlertRouter((alert_sink,), clock=clock.now),
        clock=clock.now,
    )
    control_runtime = TraderControlRuntime(
        control_store,
        account_id=settings.account_id,
        timeframe=settings.primary_timeframe,
        market_stale_threshold_seconds=settings.market_stale_threshold_seconds,
        lease_ttl_seconds=settings.lease_ttl_seconds,
        heartbeat_interval_seconds=settings.lease_heartbeat_interval_seconds,
        observability=observability,
        clock=clock.now,
        enable_background_task=False,
    )
    source = QueueEventSource()

    with session_scope(session_factory) as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        repositories.balance_snapshots.save(_balance_snapshot(clock.now() - timedelta(minutes=20)))

    oms_service = build_default_trader_oms_service(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        observability=observability,
        execution_gateway=PaperExecutionAdapter(
            cost_model=settings.paper_cost_model,
            clock=lambda: clock.now() + timedelta(seconds=3),
        ),
    )
    reconciliation_runtime = None
    if with_reconciliation:
        reconciliation_runtime = TraderReconciliationRuntime(
            SessionFactoryBackedReconciliationStore(session_factory),
            oms_service=build_default_trader_oms_service(
                settings=settings,
                session_factory=session_factory,
                control_store=control_store,
                observability=observability,
                execution_gateway=PaperExecutionAdapter(
                    cost_model=settings.paper_cost_model,
                    clock=lambda: clock.now() + timedelta(seconds=3),
                ),
            ),
            control_store=control_store,
            account_id=settings.account_id,
            exchange=settings.exchange,
            cost_model=settings.paper_cost_model,
            control_runtime=control_runtime,
            observability=observability,
            reconciliation_interval_seconds=3600,
            clock=clock.now,
            enable_background_task=False,
        )

    trader = TraderService(
        source,
        runtime_state=TraderRuntimeState(instance_id="instance-A"),
        pipeline=TraderPipelinePorts(
            strategy=BaselineMomentumStrategy(account_id=settings.account_id),
            risk=OmsSignalRiskRouter(
                oms_service=oms_service,
                symbol_rules=settings.symbol_rules,
                control_runtime=control_runtime,
            ),
        ),
        control_runtime=control_runtime,
        reconciliation_runtime=reconciliation_runtime,
    )
    return E2EHarness(
        settings=settings,
        clock=clock,
        engine=engine,
        session_factory=session_factory,
        control_store=control_store,
        control_runtime=control_runtime,
        source=source,
        trader=trader,
        alert_sink=alert_sink,
        observability=observability,
    )


def _seed_reconciliation_drift(harness: E2EHarness) -> tuple[UUID, UUID]:
    filled_signal = _signal(
        signal_id=UUID("22222222-2222-4222-8222-222222222222"),
        target_position=Decimal("100"),
        event_time=BASE_TIME - timedelta(minutes=20),
    )
    filled_intent = _active_order_intent(
        signal=filled_signal,
        order_intent_id=UUID("33333333-3333-4333-8333-333333333333"),
        side=OrderSide.BUY,
        qty=Decimal("100"),
        reduce_only=False,
        created_at=BASE_TIME - timedelta(minutes=20) + timedelta(seconds=1),
    )
    filled_order = create_order_from_intent(
        filled_intent,
        submitted_at=BASE_TIME - timedelta(minutes=20) + timedelta(seconds=2),
    )
    filled_order = filled_order.transition_to(
        OrderStatus.ACK,
        updated_at=BASE_TIME - timedelta(minutes=20) + timedelta(seconds=2),
    ).transition_to(
        OrderStatus.FILLED,
        filled_qty=Decimal("100"),
        avg_fill_price=Decimal("39.50"),
        updated_at=BASE_TIME - timedelta(minutes=20) + timedelta(seconds=3),
    )
    filled_fill = Fill(
        id=UUID("44444444-4444-4444-8444-444444444444"),
        order_id=filled_order.id,
        trader_run_id=FILLED_RUN_ID,
        exchange_fill_id="paper-fill-e2e-drift-001",
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        side=OrderSide.BUY,
        qty=Decimal("100"),
        price=Decimal("39.50"),
        fee=Decimal("1.2245"),
        fee_asset="CNY",
        liquidity_type=LiquidityType.TAKER,
        fill_time=BASE_TIME - timedelta(minutes=20) + timedelta(seconds=3),
        created_at=BASE_TIME - timedelta(minutes=20) + timedelta(seconds=3),
    )
    opening_signal = _signal(
        signal_id=UUID("55555555-5555-4555-8555-555555555555"),
        target_position=Decimal("200"),
        event_time=BASE_TIME - timedelta(minutes=5),
    )
    opening_intent_id = UUID("66666666-6666-4666-8666-666666666666")
    opening_intent = _active_order_intent(
        signal=opening_signal,
        order_intent_id=opening_intent_id,
        side=OrderSide.BUY,
        qty=Decimal("100"),
        reduce_only=False,
        created_at=BASE_TIME - timedelta(minutes=5),
    )
    reduce_signal = _signal(
        signal_id=UUID("77777777-7777-4777-8777-777777777777"),
        target_position=Decimal("0"),
        event_time=BASE_TIME - timedelta(minutes=4),
        signal_type=SignalType.EXIT,
    )
    reduce_intent_id = UUID("88888888-8888-4888-8888-888888888888")
    reduce_intent = _active_order_intent(
        signal=reduce_signal,
        order_intent_id=reduce_intent_id,
        side=OrderSide.SELL,
        qty=Decimal("100"),
        reduce_only=True,
        created_at=BASE_TIME - timedelta(minutes=4),
    )

    with harness.session_factory.begin() as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        repositories.signals.save(filled_signal)
        repositories.signals.save(opening_signal)
        repositories.signals.save(reduce_signal)
        repositories.order_intents.save(filled_intent)
        repositories.order_intents.save(opening_intent)
        repositories.order_intents.save(reduce_intent)
        repositories.orders.save(filled_order)
        repositories.orders.save(
            create_order_from_intent(
                opening_intent,
                status=OrderStatus.NEW,
                submitted_at=BASE_TIME - timedelta(minutes=5),
            )
        )
        repositories.orders.save(
            create_order_from_intent(
                reduce_intent,
                status=OrderStatus.NEW,
                submitted_at=BASE_TIME - timedelta(minutes=4),
            )
        )
        repositories.fills.save(filled_fill)
        repositories.positions.save(
            Position(
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
                updated_at=BASE_TIME - timedelta(minutes=19),
            )
        )
        repositories.balance_snapshots.save(
            _balance_snapshot(BASE_TIME - timedelta(minutes=30))
        )
        repositories.balance_snapshots.save(
            BalanceSnapshot(
                account_id="paper_account_001",
                exchange="cn_equity",
                asset="CNY",
                total=Decimal("100000"),
                available=Decimal("100000"),
                locked=Decimal("0"),
                snapshot_time=BASE_TIME - timedelta(minutes=19),
                created_at=BASE_TIME - timedelta(minutes=19),
            )
        )

    return opening_intent_id, reduce_intent_id


async def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out waiting for test condition")


@pytest.mark.asyncio
async def test_e2e_baseline_strategy_executes_full_paper_trading_loop(tmp_path: Path) -> None:
    harness = _build_harness(tmp_path, database_name="e2e_full_loop.sqlite3")

    try:
        run_task = asyncio.create_task(harness.trader.run())
        await harness.source.publish(
            _bar_event(event_time=harness.clock.now(), close=Decimal("39.50"))
        )
        await harness.source.finish()
        await run_task

        with harness.create_client() as client:
            positions = client.get("/v1/positions")
            active_orders = client.get("/v1/orders/active")
            replay_events = client.get("/v1/diagnostics/replay-events", params={"limit": 20})

        assert positions.status_code == 200
        assert positions.json()["positions"][0]["symbol"] == "600036.SH"
        assert Decimal(positions.json()["positions"][0]["qty"]) == Decimal("400")
        assert Decimal(positions.json()["positions"][0]["sellable_qty"]) == Decimal("0")
        assert active_orders.status_code == 200
        assert active_orders.json()["orders"] == []
        assert replay_events.status_code == 200

        event_types = [event["event_type"] for event in replay_events.json()["events"]]
        assert len(event_types) == 8
        assert event_types.count("oms.order_intent_persisted") == 1
        assert event_types.count("oms.order_persisted") == 1
        assert event_types.count("oms.execution_submission_requested") == 1
        assert event_types.count("execution.order_updated") == 2
        assert event_types.count("execution.fill_recorded") == 1
        assert event_types.count("portfolio.position_updated") == 1
        assert event_types.count("portfolio.balance_updated") == 1

        with session_scope(harness.session_factory) as session:
            order_record = session.scalar(select(OrderRecord))
            fill_record = session.scalar(select(FillRecord))

        assert order_record is not None
        assert order_record.status == "FILLED"
        assert fill_record is not None
        assert fill_record.qty == Decimal("400")
    finally:
        harness.dispose()


@pytest.mark.asyncio
async def test_e2e_api_kill_switch_blocks_new_opening_orders(tmp_path: Path) -> None:
    harness = _build_harness(tmp_path, database_name="e2e_kill_switch.sqlite3")

    try:
        with harness.create_client() as client:
            run_task = asyncio.create_task(harness.trader.run())

            await harness.source.publish(
                _bar_event(
                    event_time=harness.clock.now(),
                    close=MARKET_STATE.previous_close,
                )
            )
            await _wait_until(lambda: harness.trader.readiness_payload()["status"] == "ready")

            enable_kill_switch = client.post("/v1/controls/kill-switch/enable")
            assert enable_kill_switch.status_code == 200
            assert enable_kill_switch.json()["control_state"] == "kill_switch"

            harness.clock.advance(timedelta(seconds=5))
            await harness.source.publish(
                _bar_event(event_time=harness.clock.now(), close=Decimal("39.50"))
            )
            await harness.source.finish()
            await run_task

            positions = client.get("/v1/positions")
            active_orders = client.get("/v1/orders/active")

        assert positions.status_code == 200
        assert positions.json()["positions"] == []
        assert active_orders.status_code == 200
        assert active_orders.json()["orders"] == []

        with session_scope(harness.session_factory) as session:
            order_count = session.query(OrderRecord).count()
            risk_payload = session.scalar(
                select(EventLogRecord.payload_json).where(
                    EventLogRecord.event_type == "oms.risk_rejected"
                )
            )

        assert order_count == 0
        assert risk_payload is not None
        assert risk_payload["risk_result"]["reason_code"] == "KILL_SWITCH_REDUCE_ONLY"
    finally:
        harness.dispose()


@pytest.mark.asyncio
async def test_e2e_reconciliation_drift_engages_protection_mode_and_blocks_reentry(
    tmp_path: Path,
) -> None:
    harness = _build_harness(
        tmp_path,
        database_name="e2e_reconciliation.sqlite3",
        with_reconciliation=True,
    )
    opening_intent_id, reduce_intent_id = _seed_reconciliation_drift(harness)

    try:
        with harness.create_client() as client:
            run_task = asyncio.create_task(harness.trader.run())
            await _wait_until(
                lambda: harness.control_store.get_control_snapshot(
                    harness.settings.account_id
                ).protection_mode_active
            )

            status = client.get("/v1/status")
            active_orders = client.get("/v1/orders/active")

            assert status.status_code == 200
            assert status.json()["control_state"] == "protection_mode"
            assert active_orders.status_code == 200
            assert len(active_orders.json()["orders"]) == 1
            assert active_orders.json()["orders"][0]["reduce_only"] is True

            harness.clock.advance(timedelta(seconds=5))
            await harness.source.publish(
                _bar_event(event_time=harness.clock.now(), close=Decimal("39.50"))
            )
            await harness.source.finish()
            await run_task

            replay_events = client.get("/v1/diagnostics/replay-events", params={"limit": 50})

        assert replay_events.status_code == 200
        replay_event_types = [event["event_type"] for event in replay_events.json()["events"]]
        assert "reconciliation.drift_detected" in replay_event_types
        assert "reconciliation.protection_mode_engaged" in replay_event_types

        with session_scope(harness.session_factory) as session:
            opening_order = session.get(OrderRecord, build_order_id_for_intent(opening_intent_id))
            reduce_order = session.get(OrderRecord, build_order_id_for_intent(reduce_intent_id))
            risk_payload = session.scalar(
                select(EventLogRecord.payload_json)
                .where(EventLogRecord.event_type == "oms.risk_rejected")
                .order_by(EventLogRecord.event_time.desc(), EventLogRecord.id.desc())
            )

        assert opening_order is not None
        assert opening_order.status == "CANCELED"
        assert reduce_order is not None
        assert reduce_order.status == "NEW"
        assert risk_payload is not None
        assert risk_payload["risk_result"]["reason_code"] == "PROTECTION_MODE_REDUCE_ONLY"
        assert harness.trader.runtime_state.control_state is RiskControlState.PROTECTION_MODE
    finally:
        harness.dispose()
