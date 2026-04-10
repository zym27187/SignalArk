from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from apps.trader.control_plane import TraderControlPlaneStore, TraderControlRuntime
from apps.trader.oms import build_default_trader_oms_service
from apps.trader.runtime import TraderRuntimeState
from apps.trader.service import (
    OmsSignalRiskRouter,
    TraderEventContext,
    TraderPipelinePorts,
    TraderService,
)
from sqlalchemy import select
from src.config import Settings
from src.domain.events import BarEvent
from src.domain.execution import ExecutionReport
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.portfolio import BalanceSnapshot
from src.domain.strategy import BaselineMomentumStrategy, Signal, SignalType
from src.infra.db import (
    EventLogRecord,
    FillRecord,
    OrderIntentRecord,
    OrderRecord,
    SignalRecord,
    SqlAlchemyRepositories,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from src.infra.exchanges import PaperExecutionAdapter
from src.infra.observability import AlertRouter, RecordingAlertSink, SignalArkObservability
from tests.support.migrations import upgrade_database

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 1, 14, 0, tzinfo=SHANGHAI)
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


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'phase6b_runtime.sqlite3'}"


def _bar_event(
    *,
    event_time: datetime = BASE_TIME,
    market_state: MarketStateSnapshot | None = MARKET_STATE,
    close: Decimal = Decimal("39.50"),
) -> BarEvent:
    bar_end = event_time
    bar_start = bar_end - timedelta(minutes=15)
    return BarEvent(
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        bar_start_time=bar_start,
        bar_end_time=bar_end,
        event_time=bar_end,
        ingest_time=bar_end + timedelta(seconds=2),
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


class SequenceEventSource:
    def __init__(self, events: Sequence[object]) -> None:
        self._events = list(events)
        self.closed = False

    def events(self) -> AsyncIterator[object]:
        async def _iterator() -> AsyncIterator[object]:
            for event in self._events:
                yield event

        return _iterator()

    async def aclose(self) -> None:
        self.closed = True


class BlockingEventSource:
    def __init__(self) -> None:
        self._released = asyncio.Event()
        self.closed = False

    def events(self) -> AsyncIterator[object]:
        async def _iterator() -> AsyncIterator[object]:
            await self._released.wait()
            if False:
                yield  # pragma: no cover

        return _iterator()

    async def aclose(self) -> None:
        self.closed = True
        self._released.set()


class RecordingStrategy:
    def __init__(self) -> None:
        self.events: list[BarEvent] = []
        self.contexts: list[TraderEventContext] = []

    async def on_bar(self, event: BarEvent, context: TraderEventContext) -> None:
        self.events.append(event)
        self.contexts.append(context)


class SignalReturningStrategy:
    async def on_bar(self, event: BarEvent, context: TraderEventContext) -> Signal:
        return Signal(
            id=UUID("77777777-7777-4777-8777-777777777777"),
            strategy_id="baseline_momentum_v1",
            trader_run_id=context.trader_run_uuid,
            account_id="paper_account_001",
            exchange=event.exchange,
            symbol=event.symbol,
            timeframe=event.timeframe,
            signal_type=SignalType.REBALANCE,
            target_position=Decimal("400"),
            event_time=event.event_time,
            created_at=event.event_time + timedelta(seconds=1),
            reason_summary="integration test signal routing",
        )


class NoFillExecutionGateway:
    async def submit_order(self, order, order_intent) -> ExecutionReport:
        return ExecutionReport()

    async def cancel_order(self, order) -> ExecutionReport:
        return ExecutionReport()


def _balance_snapshot() -> BalanceSnapshot:
    snapshot_time = BASE_TIME - timedelta(minutes=20)
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


def _build_store(
    tmp_path: Path,
    clock: MutableClock,
) -> tuple[TraderControlPlaneStore, object, object]:
    database_url = _database_url(tmp_path)
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    store = TraderControlPlaneStore(session_factory, clock=clock.now)
    return store, session_factory, engine


def _control_runtime(
    store: TraderControlPlaneStore,
    clock: MutableClock,
    sink: RecordingAlertSink | None = None,
) -> TraderControlRuntime:
    alert_sinks = () if sink is None else (sink,)
    return TraderControlRuntime(
        store,
        account_id="paper_account_001",
        timeframe="15m",
        market_stale_threshold_seconds=120,
        lease_ttl_seconds=15,
        heartbeat_interval_seconds=5,
        observability=SignalArkObservability(
            service="tests",
            alert_router=AlertRouter(alert_sinks, clock=clock.now),
            clock=clock.now,
        ),
        clock=clock.now,
        enable_background_task=False,
    )


def test_control_plane_store_requires_migrated_control_plane_tables(tmp_path: Path) -> None:
    clock = MutableClock(BASE_TIME)
    engine = create_database_engine(_database_url(tmp_path))
    session_factory = create_session_factory(engine)
    store = TraderControlPlaneStore(session_factory, clock=clock.now)

    try:
        with pytest.raises(
            RuntimeError,
            match="Control-plane schema is missing required tables",
        ):
            store.ensure_schema()
    finally:
        engine.dispose()


def test_control_plane_store_can_take_over_stale_local_owner_before_ttl(tmp_path: Path) -> None:
    clock = MutableClock(BASE_TIME)
    database_url = _database_url(tmp_path)
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    store = TraderControlPlaneStore(
        session_factory,
        clock=clock.now,
        hostname="zymdeMac-mini.local",
        pid_exists=lambda pid: pid != 70736,
    )

    try:
        first = store.acquire_lease(
            account_id="paper_account_001",
            instance_id="zymdeMac-mini.local:70736",
            ttl_seconds=15,
            now=clock.now(),
        )
        assert first.accepted is True
        assert first.snapshot.owner_instance_id == "zymdeMac-mini.local:70736"
        assert first.snapshot.fencing_token == 1

        clock.advance(timedelta(seconds=1))
        second = store.acquire_lease(
            account_id="paper_account_001",
            instance_id="zymdeMac-mini.local:70737",
            ttl_seconds=15,
            now=clock.now(),
        )

        assert second.accepted is True
        assert second.message == "lease_taken_over_stale_local_owner"
        assert second.snapshot.owner_instance_id == "zymdeMac-mini.local:70737"
        assert second.snapshot.fencing_token == 2
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_trader_runtime_rejects_second_active_instance_for_same_account(
    tmp_path: Path,
) -> None:
    clock = MutableClock(BASE_TIME)
    store, _, engine = _build_store(tmp_path, clock)
    trader_one = TraderService(
        BlockingEventSource(),
        runtime_state=TraderRuntimeState(instance_id="instance-A"),
        control_runtime=_control_runtime(store, clock),
    )
    trader_two = TraderService(
        BlockingEventSource(),
        runtime_state=TraderRuntimeState(instance_id="instance-B"),
        control_runtime=_control_runtime(store, clock),
    )

    await trader_one.start()

    assert trader_one.runtime_state.single_active.status == "acquired"

    with pytest.raises(
        RuntimeError,
        match="Single-active trader lease is held by another instance",
    ):
        await trader_two.start()

    assert trader_two.runtime_state.single_active.status == "rejected"

    await trader_one.stop(reason="test_shutdown")
    engine.dispose()


@pytest.mark.asyncio
async def test_trader_runtime_skips_strategy_when_strategy_is_paused(tmp_path: Path) -> None:
    clock = MutableClock(BASE_TIME)
    store, _, engine = _build_store(tmp_path, clock)
    store.set_strategy_enabled(account_id="paper_account_001", enabled=False)
    strategy = RecordingStrategy()
    trader = TraderService(
        SequenceEventSource((_bar_event(),)),
        runtime_state=TraderRuntimeState(instance_id="instance-A"),
        pipeline=TraderPipelinePorts(strategy=strategy),
        control_runtime=_control_runtime(store, clock),
    )

    await trader.run()

    assert strategy.events == []
    assert trader.runtime_snapshot()["control_state"] == "strategy_paused"
    assert trader.runtime_snapshot()["last_ignored_bar_reason"] == "strategy_paused"
    engine.dispose()


@pytest.mark.asyncio
async def test_trader_runtime_becomes_not_ready_after_lease_takeover(tmp_path: Path) -> None:
    clock = MutableClock(BASE_TIME)
    store, _, engine = _build_store(tmp_path, clock)
    sink = RecordingAlertSink()
    control_runtime = _control_runtime(store, clock, sink)
    trader = TraderService(
        BlockingEventSource(),
        runtime_state=TraderRuntimeState(instance_id="instance-A"),
        control_runtime=control_runtime,
    )

    await trader.start()
    try:
        assert trader.readiness_payload()["status"] == "not_ready"

        clock.advance(timedelta(seconds=5))
        await control_runtime.observe_bar(_bar_event(event_time=clock.now()))

        assert trader.readiness_payload()["status"] == "ready"

        clock.advance(timedelta(seconds=16))
        takeover = store.acquire_lease(
            account_id="paper_account_001",
            instance_id="instance-B",
            ttl_seconds=15,
            now=clock.now(),
        )
        assert takeover.accepted is True

        await control_runtime.refresh(reason="lease_takeover", force_heartbeat=False)

        assert trader.readiness_payload()["status"] == "not_ready"
        assert trader.runtime_state.single_active.status == "lost"
        assert control_runtime.submission_guard() is None
        assert [event.event_name for event in sink.events] == ["runtime.lease_lost"]
    finally:
        await trader.stop(reason="test_shutdown")

    engine.dispose()


@pytest.mark.asyncio
async def test_trader_runtime_emits_alert_when_protection_mode_is_observed(
    tmp_path: Path,
) -> None:
    clock = MutableClock(BASE_TIME)
    store, _, engine = _build_store(tmp_path, clock)
    sink = RecordingAlertSink()
    control_runtime = _control_runtime(store, clock, sink)
    trader = TraderService(
        BlockingEventSource(),
        runtime_state=TraderRuntimeState(instance_id="instance-A"),
        control_runtime=control_runtime,
    )

    await trader.start()
    try:
        clock.advance(timedelta(seconds=5))
        await control_runtime.observe_bar(_bar_event(event_time=clock.now()))
        assert trader.readiness_payload()["status"] == "ready"

        store.set_protection_mode(account_id="paper_account_001", active=True)
        await control_runtime.refresh(reason="protection_mode_test", force_heartbeat=False)

        assert trader.runtime_state.control_state is not None
        assert trader.runtime_state.control_state.value == "protection_mode"
        assert [event.event_name for event in sink.events] == ["control.protection_mode_entered"]
    finally:
        await trader.stop(reason="test_shutdown")

    engine.dispose()


@pytest.mark.asyncio
async def test_trader_runtime_requires_market_state_before_it_becomes_ready(
    tmp_path: Path,
) -> None:
    clock = MutableClock(BASE_TIME)
    store, _, engine = _build_store(tmp_path, clock)
    control_runtime = _control_runtime(store, clock)
    trader = TraderService(
        BlockingEventSource(),
        runtime_state=TraderRuntimeState(instance_id="instance-A"),
        control_runtime=control_runtime,
    )

    await trader.start()
    try:
        clock.advance(timedelta(seconds=5))
        await control_runtime.observe_bar(_bar_event(event_time=clock.now(), market_state=None))

        readiness = trader.readiness_payload()
        assert readiness["status"] == "not_ready"
        assert readiness["market_state_available"] is False
        assert readiness["reason"] == "market_state_missing"
    finally:
        await trader.stop(reason="test_shutdown")

    engine.dispose()


@pytest.mark.asyncio
async def test_trader_runtime_routes_baseline_strategy_signal_into_oms_pipeline(
    tmp_path: Path,
) -> None:
    clock = MutableClock(BASE_TIME)
    store, session_factory, engine = _build_store(tmp_path, clock)
    settings = Settings(postgres_dsn=_database_url(tmp_path))
    observability = SignalArkObservability(
        service="tests",
        alert_router=AlertRouter((), clock=clock.now),
        clock=clock.now,
    )
    control_runtime = _control_runtime(store, clock)
    oms_service = build_default_trader_oms_service(
        settings=settings,
        session_factory=session_factory,
        control_store=store,
        observability=observability,
        execution_gateway=NoFillExecutionGateway(),
    )
    trader = TraderService(
        SequenceEventSource((_bar_event(),)),
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
    )

    await trader.run()

    with session_scope(session_factory) as session:
        signal_record = session.query(SignalRecord).one()
        order_intent_count = session.query(OrderIntentRecord).count()
        order_count = session.query(OrderRecord).count()

    assert signal_record.strategy_id == "baseline_momentum_v1"
    assert signal_record.target_position == Decimal("400")
    assert order_intent_count == 1
    assert order_count == 1
    engine.dispose()


@pytest.mark.asyncio
async def test_trader_runtime_runs_baseline_strategy_through_paper_execution(
    tmp_path: Path,
) -> None:
    clock = MutableClock(BASE_TIME)
    store, session_factory, engine = _build_store(tmp_path, clock)
    settings = Settings(postgres_dsn=_database_url(tmp_path))
    observability = SignalArkObservability(
        service="tests",
        alert_router=AlertRouter((), clock=clock.now),
        clock=clock.now,
    )
    control_runtime = _control_runtime(store, clock)
    with session_scope(session_factory) as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        repositories.balance_snapshots.save(_balance_snapshot())

    oms_service = build_default_trader_oms_service(
        settings=settings,
        session_factory=session_factory,
        control_store=store,
        observability=observability,
        execution_gateway=PaperExecutionAdapter(
            cost_model=settings.paper_cost_model,
            clock=lambda: clock.now() + timedelta(seconds=3),
        ),
    )
    trader = TraderService(
        SequenceEventSource((_bar_event(close=Decimal("39.50")),)),
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
    )

    await trader.run()

    with session_scope(session_factory) as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        signal_record = session.query(SignalRecord).one()
        order_record = session.query(OrderRecord).one()
        fill_record = session.query(FillRecord).one()
        event_types = tuple(
            session.scalars(
                select(EventLogRecord.event_type).order_by(
                    EventLogRecord.created_at.asc(),
                    EventLogRecord.id.asc(),
                )
            )
        )
        order_intent_payload = session.scalar(
            select(EventLogRecord.payload_json).where(
                EventLogRecord.event_type == "oms.order_intent_persisted"
            )
        )
        position = repositories.positions.get_by_symbol(
            account_id="paper_account_001",
            exchange="cn_equity",
            symbol="600036.SH",
        )
        latest_balance = repositories.recovery.load_runtime_state(
            account_id="paper_account_001",
            trader_run_id=UUID(trader.runtime_state.trader_run_id),
            event_limit=20,
        ).latest_balance_snapshots[0]

    snapshot = trader.runtime_snapshot()

    assert snapshot["last_strategy_id"] == "baseline_momentum_v1"
    assert snapshot["last_strategy_input_snapshot"]["entry_threshold_pct"] == "0.0500"
    assert snapshot["last_strategy_input_snapshot"]["momentum_pct"] == "0.0760"
    assert snapshot["last_strategy_signal_snapshot"]["signal_type"] == "REBALANCE"
    assert snapshot["last_strategy_signal_snapshot"]["target_position"] == "400"
    assert snapshot["last_strategy_reason_summary"] is not None
    assert "rebalance to 400" in snapshot["last_strategy_reason_summary"]
    assert signal_record.reason_summary == snapshot["last_strategy_reason_summary"]
    assert order_record.status == "FILLED"
    assert fill_record.qty == Decimal("400")
    assert order_intent_payload is not None
    assert order_intent_payload["strategy_input_snapshot"]["momentum_pct"] == "0.0760"
    assert order_intent_payload["strategy_signal_snapshot"]["signal_type"] == "REBALANCE"
    assert order_intent_payload["reason_summary"] == snapshot["last_strategy_reason_summary"]
    assert position is not None
    assert position.qty == Decimal("400")
    assert position.sellable_qty == Decimal("0")
    assert latest_balance.available == Decimal("84195.1020")
    assert latest_balance.total == Decimal("84195.1020")
    assert len(event_types) == 8
    assert event_types.count("oms.order_intent_persisted") == 1
    assert event_types.count("oms.order_persisted") == 1
    assert event_types.count("oms.execution_submission_requested") == 1
    assert event_types.count("execution.order_updated") == 2
    assert event_types.count("execution.fill_recorded") == 1
    assert event_types.count("portfolio.position_updated") == 1
    assert event_types.count("portfolio.balance_updated") == 1
    engine.dispose()


@pytest.mark.asyncio
async def test_trader_runtime_routes_strategy_signal_into_oms_pipeline(
    tmp_path: Path,
) -> None:
    clock = MutableClock(BASE_TIME)
    store, session_factory, engine = _build_store(tmp_path, clock)
    settings = Settings(postgres_dsn=_database_url(tmp_path))
    observability = SignalArkObservability(
        service="tests",
        alert_router=AlertRouter((), clock=clock.now),
        clock=clock.now,
    )
    control_runtime = _control_runtime(store, clock)
    oms_service = build_default_trader_oms_service(
        settings=settings,
        session_factory=session_factory,
        control_store=store,
        observability=observability,
        execution_gateway=NoFillExecutionGateway(),
    )
    trader = TraderService(
        SequenceEventSource((_bar_event(),)),
        runtime_state=TraderRuntimeState(instance_id="instance-A"),
        pipeline=TraderPipelinePorts(
            strategy=SignalReturningStrategy(),
            risk=OmsSignalRiskRouter(
                oms_service=oms_service,
                symbol_rules=settings.symbol_rules,
                control_runtime=control_runtime,
            ),
        ),
        control_runtime=control_runtime,
    )

    await trader.run()

    with session_scope(session_factory) as session:
        signal_count = session.query(SignalRecord).count()
        order_intent_count = session.query(OrderIntentRecord).count()
        order_count = session.query(OrderRecord).count()

    assert signal_count == 1
    assert order_intent_count == 1
    assert order_count == 1
    assert trader.runtime_snapshot()["pipeline"]["risk"]["status"] == "bound"
    assert trader.runtime_snapshot()["pipeline"]["oms"]["status"] == "bound"
    engine.dispose()
