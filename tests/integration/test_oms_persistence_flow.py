from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from alembic.config import Config
from apps.trader.oms import RepositoryBackedOmsPersistence, TraderOmsService
from sqlalchemy import func, select
from src.config.settings import AshareSymbolRule
from src.domain.execution import (
    OrderStateTransitionError,
    OrderStatus,
    build_signal_order_intent_plan,
    create_order_from_intent,
)
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.portfolio import Position, PositionStatus
from src.domain.strategy import Signal, SignalType
from src.infra.db import (
    SqlAlchemyRepositories,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from src.infra.db.models import EventLogRecord, OrderIntentRecord, OrderRecord, SignalRecord

ROOT_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = ROOT_DIR / "migrations" / "alembic.ini"
SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 1, 11, 0, tzinfo=SHANGHAI)
TRADER_RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
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


def _upgrade_database(database_url: str) -> None:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def _sqlite_database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'phase5a_oms.sqlite3'}"


@pytest.fixture
def session_factory(tmp_path: Path):
    database_url = _sqlite_database_url(tmp_path)
    _upgrade_database(database_url)
    engine = create_database_engine(database_url)
    try:
        yield create_session_factory(engine)
    finally:
        engine.dispose()


def _signal() -> Signal:
    return Signal(
        id=UUID("22222222-2222-4222-8222-222222222222"),
        strategy_id="baseline_momentum_v1",
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        signal_type=SignalType.REBALANCE,
        target_position=Decimal("420"),
        event_time=BASE_TIME,
        created_at=BASE_TIME + timedelta(seconds=1),
    )


def _position(*, qty: Decimal, sellable_qty: Decimal) -> Position:
    return Position(
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        qty=qty,
        sellable_qty=sellable_qty,
        avg_entry_price=Decimal("39.20") if qty > 0 else None,
        mark_price=Decimal("39.50") if qty > 0 else None,
        unrealized_pnl=Decimal("40") if qty > 0 else Decimal("0"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.OPEN if qty > 0 else PositionStatus.CLOSED,
        updated_at=BASE_TIME - timedelta(minutes=15),
    )


@pytest.mark.asyncio
async def test_oms_service_persists_signal_order_intent_order_and_market_contracts(
    session_factory,
) -> None:
    with session_scope(session_factory) as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        repositories.positions.save(_position(qty=Decimal("250"), sellable_qty=Decimal("250")))
        oms_service = TraderOmsService(RepositoryBackedOmsPersistence(repositories))

        submission = await oms_service.submit_signal(
            signal=_signal(),
            symbol_rule=SYMBOL_RULE,
            decision_price=Decimal("39.50"),
            market_context=MARKET_STATE,
            received_at=BASE_TIME + timedelta(seconds=2),
        )

        assert submission is not None
        assert submission.plan.qty == Decimal("100")
        assert submission.order_intent.status.value == "SUBMITTED"
        assert submission.order.status is OrderStatus.NEW

    with session_scope(session_factory) as session:
        signal_count = session.scalar(select(func.count()).select_from(SignalRecord))
        order_intent_record = session.scalar(select(OrderIntentRecord))
        order_record = session.scalar(select(OrderRecord))
        event_types = tuple(
            session.scalars(
                select(EventLogRecord.event_type).order_by(EventLogRecord.created_at.asc())
            )
        )

    assert signal_count == 1
    assert order_intent_record is not None
    assert order_intent_record.qty == Decimal("100")
    assert order_intent_record.decision_price == Decimal("39.50")
    assert order_intent_record.status == "SUBMITTED"
    assert order_intent_record.market_context_json == {
        "trade_date": "2026-04-01",
        "previous_close": "39.47",
        "upper_limit_price": "43.42",
        "lower_limit_price": "35.52",
        "trading_phase": "CONTINUOUS_AUCTION",
        "suspension_status": "ACTIVE",
    }
    assert order_record is not None
    assert order_record.order_intent_id == order_intent_record.id
    assert order_record.status == "NEW"
    assert event_types == (
        "oms.order_intent_persisted",
        "oms.order_persisted",
        "oms.execution_submission_requested",
    )


def test_order_repository_rejects_invalid_persisted_status_transition(session_factory) -> None:
    signal = _signal()
    position = _position(qty=Decimal("250"), sellable_qty=Decimal("250"))
    plan = build_signal_order_intent_plan(
        signal=signal,
        symbol_rule=SYMBOL_RULE,
        current_position=position,
        decision_price=Decimal("39.50"),
        market_context=MARKET_STATE,
    )
    order_intent = plan.to_order_intent(created_at=BASE_TIME + timedelta(seconds=2))
    order = create_order_from_intent(order_intent, submitted_at=BASE_TIME + timedelta(seconds=3))
    invalid_update = order.model_copy(
        update={
            "status": OrderStatus.FILLED,
            "filled_qty": order.qty,
            "avg_fill_price": Decimal("39.50"),
            "updated_at": BASE_TIME + timedelta(seconds=4),
        }
    )

    with session_scope(session_factory) as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        repositories.signals.save(signal)
        repositories.order_intents.save(order_intent)
        repositories.orders.save(order)

        with pytest.raises(OrderStateTransitionError, match="Invalid order status transition"):
            repositories.orders.save(invalid_update)
