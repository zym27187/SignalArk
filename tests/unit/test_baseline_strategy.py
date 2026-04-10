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
    *,
    close: Decimal,
    offset: int = 0,
    previous_close: Decimal | None = None,
    market_state: MarketStateSnapshot | None = MARKET_STATE,
) -> BarEvent:
    event_time = BASE_TIME + timedelta(minutes=15 * offset)
    resolved_market_state = market_state
    if market_state is not None and previous_close is not None:
        resolved_market_state = market_state.model_copy(update={"previous_close": previous_close})

    return BarEvent(
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        bar_start_time=event_time - timedelta(minutes=15),
        bar_end_time=event_time,
        event_time=event_time,
        ingest_time=event_time + timedelta(seconds=1),
        open=Decimal("39.40"),
        high=max(close, Decimal("39.55")),
        low=min(close, Decimal("39.38")),
        close=close,
        volume=Decimal("1000"),
        closed=True,
        final=True,
        source_kind="realtime",
        market_state=resolved_market_state,
    )


@pytest.mark.asyncio
async def test_baseline_momentum_strategy_waits_for_trend_confirmation_before_entry() -> None:
    strategy = BaselineMomentumStrategy(
        account_id="paper_account_001",
        trend_lookback_bars=3,
        min_trend_up_bars=2,
    )

    first = await strategy.on_bar(_bar_event(close=Decimal("39.48"), offset=0), _context())
    second = await strategy.on_bar(_bar_event(close=Decimal("39.49"), offset=1), _context())
    third = await strategy.on_bar(_bar_event(close=Decimal("39.50"), offset=2), _context())

    assert first is None
    assert second is None
    assert third is not None
    assert third.strategy_id == BASELINE_MOMENTUM_V1
    assert third.signal_type is SignalType.REBALANCE
    assert third.target_position == Decimal("200")

    warmup = strategy.build_non_signal_decision(_bar_event(close=Decimal("39.49"), offset=1))
    assert warmup is not None
    assert warmup.skip_reason == "baseline_trend_warmup"
    assert warmup.audit.input_snapshot["trend_lookback_bars_required"] == "3"


@pytest.mark.asyncio
async def test_baseline_momentum_strategy_uses_hysteresis_to_hold_until_exit_threshold_breaks(
) -> None:
    strategy = BaselineMomentumStrategy(
        account_id="paper_account_001",
        trend_lookback_bars=3,
        min_trend_up_bars=2,
    )

    await strategy.on_bar(_bar_event(close=Decimal("39.48"), offset=0), _context())
    await strategy.on_bar(_bar_event(close=Decimal("39.49"), offset=1), _context())
    entry_signal = await strategy.on_bar(_bar_event(close=Decimal("39.50"), offset=2), _context())
    hold_signal = await strategy.on_bar(_bar_event(close=Decimal("39.48"), offset=3), _context())

    assert entry_signal is not None
    assert hold_signal is not None
    assert hold_signal.signal_type is SignalType.REBALANCE
    assert hold_signal.target_position == Decimal("200")
    assert hold_signal.reason_summary is not None
    assert "hold current target" in hold_signal.reason_summary


@pytest.mark.asyncio
async def test_baseline_momentum_strategy_scales_up_position_on_stronger_confirmed_momentum(
) -> None:
    strategy = BaselineMomentumStrategy(
        account_id="paper_account_001",
        trend_lookback_bars=3,
        min_trend_up_bars=2,
    )

    await strategy.on_bar(_bar_event(close=Decimal("39.48"), offset=0), _context())
    await strategy.on_bar(_bar_event(close=Decimal("39.49"), offset=1), _context())
    reduced_signal = await strategy.on_bar(_bar_event(close=Decimal("39.50"), offset=2), _context())
    full_signal = await strategy.on_bar(_bar_event(close=Decimal("39.52"), offset=3), _context())

    assert reduced_signal is not None
    assert reduced_signal.target_position == Decimal("200")
    assert full_signal is not None
    assert full_signal.signal_type is SignalType.REBALANCE
    assert full_signal.target_position == Decimal("400")
    assert full_signal.reason_summary is not None
    assert "position_tier full" in full_signal.reason_summary


@pytest.mark.asyncio
async def test_baseline_momentum_strategy_exits_on_trailing_stop() -> None:
    strategy = BaselineMomentumStrategy(
        account_id="paper_account_001",
        trend_lookback_bars=3,
        min_trend_up_bars=2,
        exit_threshold_pct=Decimal("-0.0500"),
        trailing_stop_pct=Decimal("0.0100"),
    )

    await strategy.on_bar(_bar_event(close=Decimal("39.48"), offset=0), _context())
    await strategy.on_bar(_bar_event(close=Decimal("39.49"), offset=1), _context())
    await strategy.on_bar(_bar_event(close=Decimal("39.50"), offset=2), _context())
    await strategy.on_bar(_bar_event(close=Decimal("39.70"), offset=3), _context())
    exit_signal = await strategy.on_bar(
        _bar_event(close=Decimal("39.30"), offset=4, previous_close=Decimal("39.70")),
        _context(),
    )

    assert exit_signal is not None
    assert exit_signal.signal_type is SignalType.EXIT
    assert exit_signal.target_position == Decimal("0")
    assert exit_signal.reason_summary is not None
    assert "trailing_stop" in exit_signal.reason_summary


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
    await strategy.on_bar(_bar_event(close=Decimal("39.48"), offset=0), _context())
    await strategy.on_bar(_bar_event(close=Decimal("39.49"), offset=1), _context())
    event = _bar_event(close=Decimal("39.50"), offset=2)
    signal = await strategy.on_bar(event, _context())

    assert config.target_position == Decimal("400")
    assert config.entry_threshold_pct == Decimal("0.0005")
    assert config.exit_threshold_pct < config.entry_threshold_pct
    assert signal is not None
    audit = strategy.build_decision_audit(event, signal)
    assert audit.input_snapshot["entry_threshold_pct"] == "0.0500"
    assert audit.input_snapshot["exit_threshold_pct"] is not None
    assert audit.input_snapshot["position_tier"] == "reduced"
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
