from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from src.domain.execution import (
    Fill,
    LiquidityType,
    Order,
    OrderIntent,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.portfolio import BalanceSnapshot, Position, PositionStatus
from src.domain.strategy import Signal, SignalType
from src.infra.db import (
    EventLogEntry,
    SqlAlchemyRepositories,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from src.infra.db.models import OrderIntentRecord, SignalRecord

ROOT_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = ROOT_DIR / "migrations" / "alembic.ini"
SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 3, 31, 12, 0, tzinfo=SHANGHAI)
TRADER_RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
SIGNAL_ID = UUID("22222222-2222-4222-8222-222222222222")
ORDER_INTENT_ID = UUID("33333333-3333-4333-8333-333333333333")
ORDER_ID = UUID("44444444-4444-4444-8444-444444444444")
FILL_ID = UUID("55555555-5555-4555-8555-555555555555")
POSITION_ID = UUID("66666666-6666-4666-8666-666666666666")
BALANCE_ID = UUID("77777777-7777-4777-8777-777777777777")
EVENT_ID = UUID("88888888-8888-4888-8888-888888888888")
MARKET_STATE = MarketStateSnapshot(
    trade_date=BASE_TIME.date(),
    previous_close=Decimal("39.47"),
    upper_limit_price=Decimal("43.42"),
    lower_limit_price=Decimal("35.52"),
    trading_phase=TradingPhase.CONTINUOUS_AUCTION,
    suspension_status=SuspensionStatus.ACTIVE,
)


def _upgrade_database(database_url: str) -> None:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def _sqlite_database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'phase2.sqlite3'}"


@pytest.fixture
def migrated_engine(tmp_path: Path):
    database_url = _sqlite_database_url(tmp_path)
    _upgrade_database(database_url)
    engine = create_database_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(migrated_engine):
    return create_session_factory(migrated_engine)


def _build_signal(*, signal_id: UUID = SIGNAL_ID) -> Signal:
    return Signal(
        id=signal_id,
        strategy_id="baseline_momentum_v1",
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        signal_type=SignalType.ENTRY,
        target_position=Decimal("500"),
        confidence=Decimal("0.88"),
        reason_summary="phase-2 persistence integration test",
        event_time=BASE_TIME,
        created_at=BASE_TIME + timedelta(seconds=1),
    )


def _build_order_intent(*, signal_id: UUID, order_intent_id: UUID = ORDER_INTENT_ID) -> OrderIntent:
    return OrderIntent(
        id=order_intent_id,
        signal_id=signal_id,
        strategy_id="baseline_momentum_v1",
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        qty=Decimal("500"),
        decision_price=Decimal("39.42"),
        market_context_json=MARKET_STATE,
        idempotency_key="intent:entry:001",
        created_at=BASE_TIME + timedelta(seconds=2),
    )


def _build_order(
    *,
    order_intent_id: UUID,
    order_id: UUID = ORDER_ID,
    status: OrderStatus = OrderStatus.ACK,
    filled_qty: Decimal = Decimal("0"),
    avg_fill_price: Decimal | None = None,
    updated_at: datetime | None = None,
) -> Order:
    return Order(
        id=order_id,
        order_intent_id=order_intent_id,
        trader_run_id=TRADER_RUN_ID,
        exchange_order_id="paper-order-001",
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        qty=Decimal("500"),
        filled_qty=filled_qty,
        avg_fill_price=avg_fill_price,
        status=status,
        submitted_at=BASE_TIME + timedelta(seconds=3),
        updated_at=updated_at or BASE_TIME + timedelta(seconds=3),
    )


def _build_fill(*, order_id: UUID, fill_id: UUID = FILL_ID) -> Fill:
    return Fill(
        id=fill_id,
        order_id=order_id,
        trader_run_id=TRADER_RUN_ID,
        exchange_fill_id="paper-fill-001",
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        side=OrderSide.BUY,
        qty=Decimal("200"),
        price=Decimal("39.45"),
        fee=Decimal("1.00"),
        fee_asset="CNY",
        liquidity_type=LiquidityType.TAKER,
        fill_time=BASE_TIME + timedelta(seconds=4),
        created_at=BASE_TIME + timedelta(seconds=5),
    )


def _build_position(
    *,
    position_id: UUID = POSITION_ID,
    qty: Decimal,
    sellable_qty: Decimal,
) -> Position:
    return Position(
        id=position_id,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        qty=qty,
        sellable_qty=sellable_qty,
        avg_entry_price=Decimal("39.45") if qty > 0 else None,
        mark_price=Decimal("39.50"),
        unrealized_pnl=Decimal("10") if qty > 0 else Decimal("0"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.OPEN if qty > 0 else PositionStatus.CLOSED,
        updated_at=BASE_TIME + timedelta(seconds=6),
    )


def _build_balance_snapshot(
    *,
    balance_id: UUID,
    snapshot_time: datetime,
    total: Decimal,
    available: Decimal,
    locked: Decimal,
) -> BalanceSnapshot:
    return BalanceSnapshot(
        id=balance_id,
        account_id="paper_account_001",
        exchange="cn_equity",
        asset="CNY",
        total=total,
        available=available,
        locked=locked,
        snapshot_time=snapshot_time,
        created_at=snapshot_time + timedelta(seconds=1),
    )


def test_alembic_upgrade_creates_phase2_tables(migrated_engine) -> None:
    inspector = inspect(migrated_engine)

    assert {
        "signals",
        "order_intents",
        "orders",
        "fills",
        "positions",
        "balance_snapshots",
        "event_logs",
        "alembic_version",
    }.issubset(set(inspector.get_table_names()))

    unique_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("order_intents")
    }
    assert ("idempotency_key",) in unique_constraints
    order_intent_columns = {column["name"] for column in inspector.get_columns("order_intents")}
    assert "market_context_json" in order_intent_columns
    position_columns = {column["name"] for column in inspector.get_columns("positions")}
    assert "sellable_qty" in position_columns


def test_order_intent_idempotency_key_is_enforced_by_database(session_factory) -> None:
    with session_factory.begin() as session:
        session.add(
            SignalRecord(
                **_build_signal().model_dump(mode="python"),
            )
        )
        session.add(
            OrderIntentRecord(
                **_build_order_intent(signal_id=SIGNAL_ID).model_dump(mode="python"),
            )
        )

    with pytest.raises(IntegrityError):
        with session_factory.begin() as session:
            session.add(
                OrderIntentRecord(
                    **_build_order_intent(
                        signal_id=SIGNAL_ID,
                        order_intent_id=UUID("99999999-9999-4999-8999-999999999999"),
                    ).model_dump(mode="python"),
                )
            )


def test_repositories_support_idempotent_writes_and_recovery(session_factory) -> None:
    duplicate_intent_id = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
    updated_order_id = UUID("12121212-3434-4567-8abc-121212121212")
    duplicate_fill_id = UUID("13131313-3434-4567-8abc-131313131313")
    updated_position_id = UUID("14141414-3434-4567-8abc-141414141414")
    later_balance_id = UUID("15151515-3434-4567-8abc-151515151515")

    with session_scope(session_factory) as session:
        repositories = SqlAlchemyRepositories.from_session(session)

        signal = repositories.signals.save(_build_signal())
        order_intent = repositories.order_intents.save(_build_order_intent(signal_id=signal.id))
        duplicate_intent = repositories.order_intents.save(
            _build_order_intent(signal_id=signal.id, order_intent_id=duplicate_intent_id)
        )
        order = repositories.orders.save(_build_order(order_intent_id=order_intent.id))
        updated_order = repositories.orders.save(
            _build_order(
                order_intent_id=order_intent.id,
                order_id=updated_order_id,
                status=OrderStatus.PARTIALLY_FILLED,
                filled_qty=Decimal("200"),
                avg_fill_price=Decimal("39.45"),
                updated_at=BASE_TIME + timedelta(seconds=7),
            )
        )
        fill = repositories.fills.save(_build_fill(order_id=order.id))
        duplicate_fill = repositories.fills.save(
            _build_fill(order_id=order.id, fill_id=duplicate_fill_id)
        )
        position = repositories.positions.save(
            _build_position(qty=Decimal("200"), sellable_qty=Decimal("0"))
        )
        updated_position = repositories.positions.save(
            _build_position(
                position_id=updated_position_id,
                qty=Decimal("350"),
                sellable_qty=Decimal("250"),
            )
        )
        repositories.balance_snapshots.save(
            _build_balance_snapshot(
                balance_id=BALANCE_ID,
                snapshot_time=BASE_TIME + timedelta(seconds=8),
                total=Decimal("100000"),
                available=Decimal("95000"),
                locked=Decimal("5000"),
            )
        )
        latest_balance = repositories.balance_snapshots.save(
            _build_balance_snapshot(
                balance_id=later_balance_id,
                snapshot_time=BASE_TIME + timedelta(seconds=20),
                total=Decimal("101000"),
                available=Decimal("96000"),
                locked=Decimal("5000"),
            )
        )
        saved_event = repositories.event_logs.save(
            EventLogEntry(
                event_id=EVENT_ID,
                event_type="order.updated",
                source="paper_execution",
                trader_run_id=TRADER_RUN_ID,
                account_id="paper_account_001",
                exchange="cn_equity",
                symbol="600036.SH",
                related_object_type="order",
                related_object_id=order.id,
                event_time=BASE_TIME + timedelta(seconds=7),
                ingest_time=BASE_TIME + timedelta(seconds=8),
                created_at=BASE_TIME + timedelta(seconds=9),
                payload_json={"status": "PARTIALLY_FILLED", "filled_qty": "200"},
            )
        )

    with session_scope(session_factory) as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        recovered_state = repositories.recovery.load_runtime_state(
            account_id="paper_account_001",
            trader_run_id=TRADER_RUN_ID,
            event_limit=10,
        )

    assert signal.id == SIGNAL_ID
    assert order_intent.id == ORDER_INTENT_ID
    assert order_intent.market_state is not None
    assert order_intent.market_state.previous_close == Decimal("39.47")
    assert duplicate_intent.id == ORDER_INTENT_ID
    assert order.id == ORDER_ID
    assert updated_order.id == ORDER_ID
    assert updated_order.status is OrderStatus.PARTIALLY_FILLED
    assert fill.id == FILL_ID
    assert duplicate_fill.id == FILL_ID
    assert position.id == POSITION_ID
    assert updated_position.id == POSITION_ID
    assert updated_position.qty == Decimal("350")
    assert updated_position.sellable_qty == Decimal("250")
    assert latest_balance.snapshot_time == BASE_TIME + timedelta(seconds=20)
    assert saved_event.event_id == EVENT_ID

    assert len(recovered_state.open_orders) == 1
    assert recovered_state.open_orders[0].id == ORDER_ID
    assert recovered_state.open_orders[0].status is OrderStatus.PARTIALLY_FILLED
    assert len(recovered_state.open_positions) == 1
    assert recovered_state.open_positions[0].qty == Decimal("350")
    assert recovered_state.open_positions[0].sellable_qty == Decimal("250")
    assert len(recovered_state.latest_balance_snapshots) == 1
    assert recovered_state.latest_balance_snapshots[0].snapshot_time == BASE_TIME + timedelta(
        seconds=20
    )
    assert len(recovered_state.recent_event_logs) == 1
    assert recovered_state.recent_event_logs[0].event_id == EVENT_ID
