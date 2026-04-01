from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from apps.trader.runtime import TraderRuntimeState
from apps.trader.service import TraderEventContext, build_default_trader_service
from src.config import Settings
from src.domain.events import BarEvent
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.strategy import (
    BASELINE_MOMENTUM_V1,
    BaselineMomentumStrategy,
    SignalType,
    build_strategy,
    load_baseline_momentum_config,
)

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


def _context() -> TraderEventContext:
    runtime_state = TraderRuntimeState(trader_run_id="11111111-1111-4111-8111-111111111111")
    return TraderEventContext(
        trader_run_id=runtime_state.trader_run_id,
        instance_id=runtime_state.instance_id,
        received_at=BASE_TIME + timedelta(seconds=2),
        runtime_state=runtime_state,
    )


def _bar_event(
    *, close: Decimal, market_state: MarketStateSnapshot | None = MARKET_STATE
) -> BarEvent:
    return BarEvent(
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        bar_start_time=BASE_TIME - timedelta(minutes=15),
        bar_end_time=BASE_TIME,
        event_time=BASE_TIME,
        ingest_time=BASE_TIME + timedelta(seconds=1),
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


@pytest.mark.asyncio
async def test_baseline_momentum_strategy_targets_long_position_on_positive_momentum() -> None:
    strategy = BaselineMomentumStrategy(account_id="paper_account_001")

    signal = await strategy.on_bar(_bar_event(close=Decimal("39.50")), _context())

    assert signal is not None
    assert signal.strategy_id == BASELINE_MOMENTUM_V1
    assert signal.signal_type is SignalType.REBALANCE
    assert signal.target_position == Decimal("400")
    assert signal.reason_summary is not None
    assert "previous_close" in signal.reason_summary
    assert "threshold_pct" in signal.reason_summary


@pytest.mark.asyncio
async def test_baseline_momentum_strategy_flattens_on_non_positive_momentum() -> None:
    strategy = BaselineMomentumStrategy(account_id="paper_account_001")

    signal = await strategy.on_bar(_bar_event(close=Decimal("39.47")), _context())

    assert signal is not None
    assert signal.signal_type is SignalType.EXIT
    assert signal.target_position == Decimal("0")
    assert signal.reason_summary is not None
    assert "flatten" in signal.reason_summary


@pytest.mark.asyncio
async def test_baseline_momentum_strategy_skips_when_market_state_is_missing() -> None:
    strategy = BaselineMomentumStrategy(account_id="paper_account_001")

    signal = await strategy.on_bar(
        _bar_event(close=Decimal("39.50"), market_state=None), _context()
    )

    assert signal is None


def test_build_strategy_resolves_configured_baseline() -> None:
    strategy = build_strategy(
        strategy_id=BASELINE_MOMENTUM_V1,
        account_id="paper_account_001",
    )

    assert isinstance(strategy, BaselineMomentumStrategy)


@pytest.mark.asyncio
async def test_build_strategy_loads_repo_local_strategy_configuration() -> None:
    config = load_baseline_momentum_config(BASELINE_MOMENTUM_V1)
    strategy = build_strategy(
        strategy_id=BASELINE_MOMENTUM_V1,
        account_id="paper_account_001",
    )
    event = _bar_event(close=Decimal("39.50"))
    signal = await strategy.on_bar(event, _context())

    assert config.target_position == Decimal("400")
    assert config.entry_threshold_pct == Decimal("0.0005")
    assert signal is not None
    audit = strategy.build_decision_audit(event, signal)
    assert audit.input_snapshot["entry_threshold_pct"] == "0.0500"
    assert audit.signal_snapshot["signal_type"] == "REBALANCE"


@pytest.mark.asyncio
async def test_build_default_trader_service_autowires_baseline_strategy_pipeline() -> None:
    trader = build_default_trader_service(Settings(postgres_dsn="sqlite+pysqlite:///:memory:"))

    try:
        pipeline = trader.runtime_snapshot()["pipeline"]
        assert pipeline["strategy"]["handler_name"] == "BaselineMomentumStrategy"
        assert pipeline["risk"]["handler_name"] == "OmsSignalRiskRouter"
        assert pipeline["oms"]["handler_name"] == "TraderOmsService"
    finally:
        await trader._source.aclose()
