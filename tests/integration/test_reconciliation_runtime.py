from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from apps.trader.control_plane import TraderControlPlaneStore
from apps.trader.oms import build_default_trader_oms_service
from apps.trader.reconciliation import (
    SessionFactoryBackedReconciliationStore,
    TraderReconciliationRuntime,
)
from apps.trader.runtime import TraderRuntimeState
from sqlalchemy import select
from src.config.settings import Settings
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
from src.domain.portfolio import BalanceSnapshot, Position, PositionStatus
from src.domain.strategy import Signal, SignalType
from src.infra.db import (
    Base,
    EventLogRecord,
    SqlAlchemyRepositories,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from src.infra.exchanges import PaperExecutionAdapter
from src.infra.observability import AlertRouter, RecordingAlertSink, SignalArkObservability

SHANGHAI = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 4, 2, 10, 0, tzinfo=SHANGHAI)
PREVIOUS_DAY = NOW - timedelta(days=1)
TRADER_RUN_ID = UUID("11111111-1111-4111-8111-111111111111")


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'phase9_reconciliation.sqlite3'}"


def _settings(database_url: str) -> Settings:
    return Settings(postgres_dsn=database_url)


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
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        signal_type=signal_type,
        target_position=target_position,
        event_time=event_time,
        created_at=event_time + timedelta(seconds=1),
        reason_summary="phase-9 reconciliation test",
    )


def _order_intent(
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
        idempotency_key=f"intent:{order_intent_id}",
        status=OrderIntentStatus.SUBMITTED,
        created_at=created_at,
    )


def _baseline_balance(*, snapshot_time: datetime, total: Decimal) -> BalanceSnapshot:
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


def _reconciliation_runtime(
    *,
    settings: Settings,
    session_factory,
    control_store: TraderControlPlaneStore,
    sink: RecordingAlertSink,
    clock,
) -> TraderReconciliationRuntime:
    observability = SignalArkObservability(
        service="tests",
        alert_router=AlertRouter((sink,), clock=clock),
        clock=clock,
    )
    oms_service = build_default_trader_oms_service(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        observability=observability,
        execution_gateway=PaperExecutionAdapter(
            cost_model=settings.paper_cost_model,
            clock=clock,
        ),
    )
    return TraderReconciliationRuntime(
        SessionFactoryBackedReconciliationStore(session_factory),
        oms_service=oms_service,
        control_store=control_store,
        account_id=settings.account_id,
        exchange=settings.exchange,
        cost_model=settings.paper_cost_model,
        observability=observability,
        reconciliation_interval_seconds=3600,
        clock=clock,
        enable_background_task=False,
    )


@pytest.mark.asyncio
async def test_reconciliation_startup_recovery_releases_sellable_qty(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    settings = _settings(database_url)
    engine = create_database_engine(database_url)
    Base.metadata.create_all(bind=engine)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory, clock=lambda: NOW)
    sink = RecordingAlertSink()
    runtime = _reconciliation_runtime(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        sink=sink,
        clock=lambda: NOW,
    )

    previous_day_signal = _signal(
        signal_id=UUID("22222222-2222-4222-8222-222222222222"),
        target_position=Decimal("300"),
        event_time=PREVIOUS_DAY,
    )
    previous_day_intent = _order_intent(
        signal=previous_day_signal,
        order_intent_id=UUID("33333333-3333-4333-8333-333333333333"),
        side=OrderSide.BUY,
        qty=Decimal("300"),
        reduce_only=False,
        created_at=PREVIOUS_DAY + timedelta(seconds=1),
    )
    previous_day_order = create_order_from_intent(
        previous_day_intent,
        submitted_at=PREVIOUS_DAY + timedelta(seconds=2),
    )
    previous_day_order = previous_day_order.transition_to(
        OrderStatus.ACK,
        updated_at=PREVIOUS_DAY + timedelta(seconds=2),
    ).transition_to(
        OrderStatus.FILLED,
        filled_qty=Decimal("300"),
        avg_fill_price=Decimal("10.00"),
        updated_at=PREVIOUS_DAY + timedelta(seconds=3),
    )
    previous_day_fill = Fill(
        id=UUID("44444444-4444-4444-8444-444444444444"),
        order_id=previous_day_order.id,
        trader_run_id=TRADER_RUN_ID,
        exchange_fill_id="paper-fill-recovery-001",
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        side=OrderSide.BUY,
        qty=Decimal("300"),
        price=Decimal("10.00"),
        fee=Decimal("0.9300"),
        fee_asset="CNY",
        liquidity_type=LiquidityType.TAKER,
        fill_time=PREVIOUS_DAY + timedelta(seconds=3),
        created_at=PREVIOUS_DAY + timedelta(seconds=3),
    )
    recovered_position = Position(
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        qty=Decimal("300"),
        sellable_qty=Decimal("0"),
        avg_entry_price=Decimal("10.00"),
        mark_price=Decimal("10.00"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("-0.9300"),
        status=PositionStatus.OPEN,
        updated_at=PREVIOUS_DAY + timedelta(seconds=3),
    )

    with session_factory.begin() as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        repositories.signals.save(previous_day_signal)
        repositories.order_intents.save(previous_day_intent)
        repositories.orders.save(previous_day_order)
        repositories.fills.save(previous_day_fill)
        repositories.positions.save(recovered_position)
        repositories.balance_snapshots.save(
            _baseline_balance(
                snapshot_time=PREVIOUS_DAY - timedelta(minutes=5),
                total=Decimal("100000"),
            )
        )
        repositories.balance_snapshots.save(
            _baseline_balance(
                snapshot_time=PREVIOUS_DAY + timedelta(seconds=3),
                total=Decimal("96999.0700"),
            )
        )

    runtime_state = TraderRuntimeState(
        trader_run_id=str(TRADER_RUN_ID),
        instance_id="instance-A",
    )
    await runtime.start(runtime_state)
    try:
        with session_scope(session_factory) as session:
            repositories = SqlAlchemyRepositories.from_session(session)
            position = repositories.positions.get_by_symbol(
                account_id="paper_account_001",
                exchange="cn_equity",
                symbol="600036.SH",
            )
            event_types = tuple(
                session.scalars(
                    select(EventLogRecord.event_type).order_by(
                        EventLogRecord.event_time.asc(),
                        EventLogRecord.id.asc(),
                    )
                )
            )

        assert runtime.last_result is not None
        assert runtime.last_result.has_drift is False
        assert position is not None
        assert position.sellable_qty == Decimal("300")
        assert "portfolio.sellable_qty_released" in event_types
        assert "reconciliation.startup_recovery_completed" in event_types
        assert sink.events == []
    finally:
        await runtime.stop()
        engine.dispose()


@pytest.mark.asyncio
async def test_reconciliation_drift_enters_protection_mode_and_cancels_non_reduce_only_orders(
    tmp_path: Path,
) -> None:
    database_url = _database_url(tmp_path)
    settings = _settings(database_url)
    engine = create_database_engine(database_url)
    Base.metadata.create_all(bind=engine)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory, clock=lambda: NOW)
    sink = RecordingAlertSink()
    runtime = _reconciliation_runtime(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        sink=sink,
        clock=lambda: NOW,
    )

    filled_signal = _signal(
        signal_id=UUID("55555555-5555-4555-8555-555555555555"),
        target_position=Decimal("100"),
        event_time=NOW - timedelta(minutes=20),
    )
    filled_intent = _order_intent(
        signal=filled_signal,
        order_intent_id=UUID("66666666-6666-4666-8666-666666666666"),
        side=OrderSide.BUY,
        qty=Decimal("100"),
        reduce_only=False,
        created_at=NOW - timedelta(minutes=20) + timedelta(seconds=1),
    )
    filled_order = create_order_from_intent(
        filled_intent,
        submitted_at=NOW - timedelta(minutes=20) + timedelta(seconds=2),
    )
    filled_order = filled_order.transition_to(
        OrderStatus.ACK,
        updated_at=NOW - timedelta(minutes=20) + timedelta(seconds=2),
    ).transition_to(
        OrderStatus.FILLED,
        filled_qty=Decimal("100"),
        avg_fill_price=Decimal("39.50"),
        updated_at=NOW - timedelta(minutes=20) + timedelta(seconds=3),
    )
    filled_fill = Fill(
        id=UUID("77777777-7777-4777-8777-777777777777"),
        order_id=filled_order.id,
        trader_run_id=TRADER_RUN_ID,
        exchange_fill_id="paper-fill-drift-001",
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        side=OrderSide.BUY,
        qty=Decimal("100"),
        price=Decimal("39.50"),
        fee=Decimal("1.2245"),
        fee_asset="CNY",
        liquidity_type=LiquidityType.TAKER,
        fill_time=NOW - timedelta(minutes=20) + timedelta(seconds=3),
        created_at=NOW - timedelta(minutes=20) + timedelta(seconds=3),
    )
    opening_signal = _signal(
        signal_id=UUID("88888888-8888-4888-8888-888888888888"),
        target_position=Decimal("200"),
        event_time=NOW - timedelta(minutes=5),
    )
    opening_intent = _order_intent(
        signal=opening_signal,
        order_intent_id=UUID("99999999-9999-4999-8999-999999999999"),
        side=OrderSide.BUY,
        qty=Decimal("100"),
        reduce_only=False,
        created_at=NOW - timedelta(minutes=5),
    )
    reduce_signal = _signal(
        signal_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        target_position=Decimal("0"),
        event_time=NOW - timedelta(minutes=4),
        signal_type=SignalType.EXIT,
    )
    reduce_intent = _order_intent(
        signal=reduce_signal,
        order_intent_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        side=OrderSide.SELL,
        qty=Decimal("100"),
        reduce_only=True,
        created_at=NOW - timedelta(minutes=4),
    )

    with session_factory.begin() as session:
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
                submitted_at=NOW - timedelta(minutes=5),
            )
        )
        repositories.orders.save(
            create_order_from_intent(
                reduce_intent,
                status=OrderStatus.NEW,
                submitted_at=NOW - timedelta(minutes=4),
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
                updated_at=NOW - timedelta(minutes=19),
            )
        )
        repositories.balance_snapshots.save(
            _baseline_balance(
                snapshot_time=NOW - timedelta(minutes=30),
                total=Decimal("100000"),
            )
        )
        repositories.balance_snapshots.save(
            _baseline_balance(
                snapshot_time=NOW - timedelta(minutes=19),
                total=Decimal("100000"),
            )
        )

    runtime_state = TraderRuntimeState(
        trader_run_id=str(TRADER_RUN_ID),
        instance_id="instance-A",
    )
    await runtime.start(runtime_state)
    try:
        with session_scope(session_factory) as session:
            repositories = SqlAlchemyRepositories.from_session(session)
            opening_order = repositories.orders.get(build_order_id_for_intent(opening_intent.id))
            reduce_order = repositories.orders.get(build_order_id_for_intent(reduce_intent.id))
            event_types = tuple(
                session.scalars(
                    select(EventLogRecord.event_type).order_by(
                        EventLogRecord.event_time.asc(),
                        EventLogRecord.id.asc(),
                    )
                )
            )

        control_snapshot = control_store.get_control_snapshot(settings.account_id)

        assert runtime.last_result is not None
        assert runtime.last_result.has_drift is True
        assert control_snapshot.protection_mode_active is True
        assert opening_order is not None
        assert reduce_order is not None
        assert opening_order.status is OrderStatus.CANCELED
        assert reduce_order.status is OrderStatus.NEW
        assert "reconciliation.drift_detected" in event_types
        assert "reconciliation.protection_mode_engaged" in event_types
        assert [event.event_name for event in sink.events] == [
            "reconciliation.drift_detected",
            "reconciliation.protection_mode_engaged",
        ]
    finally:
        await runtime.stop()
        engine.dispose()
