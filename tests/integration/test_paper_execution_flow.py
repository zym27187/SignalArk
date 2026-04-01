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
from src.config.settings import AshareSymbolRule, PaperCostModel
from src.domain.execution import OrderStatus, OrderType
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.portfolio import BalanceSnapshot, Position, PositionStatus
from src.domain.strategy import Signal, SignalType
from src.infra.db import (
    EventLogRecord,
    FillRecord,
    OrderRecord,
    SqlAlchemyRepositories,
    create_database_engine,
    create_session_factory,
    session_scope,
)
from src.infra.exchanges import PaperExecutionAdapter

ROOT_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI_PATH = ROOT_DIR / "migrations" / "alembic.ini"
SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 1, 11, 30, tzinfo=SHANGHAI)
TRADER_RUN_ID = UUID("f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1f1")
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
    return f"sqlite+pysqlite:///{tmp_path / 'phase5b_paper.sqlite3'}"


@pytest.fixture
def session_factory(tmp_path: Path):
    database_url = _sqlite_database_url(tmp_path)
    _upgrade_database(database_url)
    engine = create_database_engine(database_url)
    try:
        yield create_session_factory(engine)
    finally:
        engine.dispose()


def _paper_cost_model() -> PaperCostModel:
    return PaperCostModel(
        commission=Decimal("0.0003"),
        transfer_fee=Decimal("0.00001"),
        stamp_duty_sell=Decimal("0.0005"),
    )


def _signal() -> Signal:
    return Signal(
        id=UUID("f2f2f2f2-f2f2-42f2-82f2-f2f2f2f2f2f2"),
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


@pytest.mark.asyncio
async def test_oms_service_with_paper_execution_persists_ack_fill_and_cost_events(
    session_factory,
) -> None:
    with session_scope(session_factory) as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        repositories.positions.save(_position(qty=Decimal("250"), sellable_qty=Decimal("250")))
        repositories.balance_snapshots.save(_balance_snapshot())
        oms_service = TraderOmsService(
            RepositoryBackedOmsPersistence(repositories),
            execution_gateway=PaperExecutionAdapter(
                cost_model=_paper_cost_model(),
                clock=lambda: BASE_TIME + timedelta(seconds=3),
            ),
        )

        submission = await oms_service.submit_signal(
            signal=_signal(),
            symbol_rule=SYMBOL_RULE,
            decision_price=Decimal("39.50"),
            market_context=MARKET_STATE,
            received_at=BASE_TIME + timedelta(seconds=2),
        )

        assert submission is not None
        assert submission.order.status is OrderStatus.FILLED
        assert submission.order.filled_qty == Decimal("100")

    with session_scope(session_factory) as session:
        order_record = session.scalar(select(OrderRecord))
        fill_record = session.scalar(select(FillRecord))
        repositories = SqlAlchemyRepositories.from_session(session)
        position = repositories.positions.get_by_symbol(
            account_id="paper_account_001",
            exchange="cn_equity",
            symbol="600036.SH",
        )
        recovered_state = repositories.recovery.load_runtime_state(
            account_id="paper_account_001",
            trader_run_id=TRADER_RUN_ID,
            event_limit=20,
        )
        event_types = tuple(
            session.scalars(
                select(EventLogRecord.event_type).order_by(
                    EventLogRecord.created_at.asc(),
                    EventLogRecord.id.asc(),
                )
            )
        )
        fill_event_payload = session.scalar(
            select(EventLogRecord.payload_json).where(
                EventLogRecord.event_type == "execution.fill_recorded"
            )
        )

    assert order_record is not None
    assert order_record.status == "FILLED"
    assert order_record.filled_qty == Decimal("100")
    assert order_record.avg_fill_price == Decimal("39.50")
    assert fill_record is not None
    assert fill_record.fee == Decimal("1.2245")
    assert position is not None
    assert position.qty == Decimal("350")
    assert position.sellable_qty == Decimal("250")
    assert position.realized_pnl == Decimal("-1.2245")
    assert position.mark_price == Decimal("39.5000000000")
    assert len(recovered_state.latest_balance_snapshots) == 1
    assert recovered_state.latest_balance_snapshots[0].available == Decimal("96048.7755")
    assert recovered_state.latest_balance_snapshots[0].total == Decimal("96048.7755")
    assert len(event_types) == 8
    assert event_types.count("oms.order_intent_persisted") == 1
    assert event_types.count("oms.order_persisted") == 1
    assert event_types.count("oms.execution_submission_requested") == 1
    assert event_types.count("execution.order_updated") == 2
    assert event_types.count("execution.fill_recorded") == 1
    assert event_types.count("portfolio.position_updated") == 1
    assert event_types.count("portfolio.balance_updated") == 1
    assert fill_event_payload is not None
    assert fill_event_payload["execution_source"] == "paper_execution"
    assert fill_event_payload["fill_event"]["cost_breakdown"]["commission"] == "1.1850"
    assert fill_event_payload["fill_event"]["cost_breakdown"]["total_fee"] == "1.2245"


@pytest.mark.asyncio
async def test_oms_service_with_paper_execution_rejects_non_marketable_limit_orders(
    session_factory,
) -> None:
    with session_scope(session_factory) as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        repositories.positions.save(_position(qty=Decimal("250"), sellable_qty=Decimal("250")))
        repositories.balance_snapshots.save(_balance_snapshot())
        oms_service = TraderOmsService(
            RepositoryBackedOmsPersistence(repositories),
            execution_gateway=PaperExecutionAdapter(
                cost_model=_paper_cost_model(),
                clock=lambda: BASE_TIME + timedelta(seconds=3),
            ),
        )

        submission = await oms_service.submit_signal(
            signal=_signal(),
            symbol_rule=SYMBOL_RULE,
            decision_price=Decimal("39.50"),
            market_context=MARKET_STATE,
            order_type=OrderType.LIMIT,
            price=Decimal("39.00"),
            received_at=BASE_TIME + timedelta(seconds=2),
        )

        assert submission is not None
        assert submission.order.status is OrderStatus.REJECTED

    with session_scope(session_factory) as session:
        order_record = session.scalar(select(OrderRecord))
        fill_count = session.scalar(select(func.count()).select_from(FillRecord))
        reject_payload = session.scalar(
            select(EventLogRecord.payload_json).where(
                EventLogRecord.event_type == "execution.order_updated"
            )
        )

    assert order_record is not None
    assert order_record.status == "REJECTED"
    assert fill_count == 0
    assert reject_payload is not None
    assert reject_payload["order_update"]["error_code"] == "RESTING_LIMIT_NOT_SUPPORTED"


def test_oms_service_recovery_releases_sellable_qty_for_the_new_trade_date(
    session_factory,
) -> None:
    with session_scope(session_factory) as session:
        repositories = SqlAlchemyRepositories.from_session(session)
        repositories.positions.save(
            Position(
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
        )
        repositories.balance_snapshots.save(_balance_snapshot())
        oms_service = TraderOmsService(RepositoryBackedOmsPersistence(repositories))

        recovered_state = oms_service.load_recovery_state(
            account_id="paper_account_001",
            trader_run_id=TRADER_RUN_ID,
            event_limit=10,
            effective_trade_date=BASE_TIME.date(),
        )

    assert len(recovered_state.open_positions) == 1
    assert recovered_state.open_positions[0].qty == Decimal("300")
    assert recovered_state.open_positions[0].sellable_qty == Decimal("300")
    assert len(recovered_state.latest_balance_snapshots) == 1
    assert recovered_state.latest_balance_snapshots[0].available == Decimal("100000")
