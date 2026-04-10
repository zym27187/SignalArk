from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from apps.research import build_default_backtest_runner
from apps.trader.runtime import TraderRuntimeState
from apps.trader.service import TraderEventContext
from src.config import Settings
from src.domain.events import BarEvent
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.strategy import BaselineMomentumStrategy
from src.domain.strategy.ai import AiBarJudgeStrategy, AiDecisionRequest, AiStrategyDecision
from src.services.backtest import BacktestStrategyContext

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


def _settings() -> Settings:
    return Settings(postgres_dsn="sqlite+pysqlite:///:memory:")


def _bar_event(
    *,
    event_time: datetime = BASE_TIME,
    close: Decimal = Decimal("39.50"),
    market_state: MarketStateSnapshot = MARKET_STATE,
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
        source_kind="historical",
        market_state=market_state,
    )


def _trader_context() -> TraderEventContext:
    runtime_state = TraderRuntimeState(trader_run_id="11111111-1111-4111-8111-111111111111")
    return TraderEventContext(
        trader_run_id=runtime_state.trader_run_id,
        instance_id=runtime_state.instance_id,
        received_at=BASE_TIME + timedelta(seconds=2),
        runtime_state=runtime_state,
    )


class HoldOnlyAiProvider:
    async def decide(self, request: AiDecisionRequest) -> AiStrategyDecision:
        del request
        return AiStrategyDecision(
            action="hold",
            confidence=Decimal("0.91"),
            target_position=None,
            reason_summary="market regime is mixed",
            provider_name="scripted_provider",
        )


@pytest.mark.asyncio
async def test_baseline_strategy_accepts_backtest_context_with_same_signal_semantics() -> None:
    trader_strategy = BaselineMomentumStrategy(account_id="paper_account_001")
    backtest_strategy = BaselineMomentumStrategy(account_id="paper_account_001")
    trader_context = _trader_context()
    backtest_context = BacktestStrategyContext(
        trader_run_uuid=trader_context.trader_run_uuid,
        received_at=trader_context.received_at,
    )
    events = (
        _bar_event(close=Decimal("39.48")),
        _bar_event(event_time=BASE_TIME + timedelta(minutes=15), close=Decimal("39.49")),
        _bar_event(event_time=BASE_TIME + timedelta(minutes=30), close=Decimal("39.52")),
    )

    trader_signal = None
    backtest_signal = None
    for event in events:
        trader_signal = await trader_strategy.on_bar(event, trader_context)
        backtest_signal = await backtest_strategy.on_bar(event, backtest_context)

    assert trader_signal is not None
    assert backtest_signal is not None
    assert backtest_signal.strategy_id == trader_signal.strategy_id
    assert backtest_signal.signal_type is trader_signal.signal_type
    assert backtest_signal.target_position == trader_signal.target_position
    assert backtest_signal.event_time == trader_signal.event_time
    assert backtest_signal.created_at == trader_signal.created_at
    assert backtest_signal.reason_summary == trader_signal.reason_summary


@pytest.mark.asyncio
async def test_default_backtest_runner_builds_stable_manifest_for_identical_inputs() -> None:
    runner = build_default_backtest_runner(
        _settings(),
        initial_cash=Decimal("100000"),
        slippage_bps=Decimal("5"),
    )
    bars = (_bar_event(),)

    first_result = await runner.run(bars)
    second_result = await runner.run(bars)

    assert first_result.manifest.run_id == second_result.manifest.run_id
    assert (
        first_result.manifest.manifest_fingerprint
        == second_result.manifest.manifest_fingerprint
    )
    assert first_result.manifest.strategy.strategy_id == "baseline_momentum_v1"
    assert first_result.manifest.strategy.parameters["target_position"] == "400"
    assert first_result.manifest.cost_assumptions.slippage_bps == Decimal("5")
    assert (
        first_result.manifest.dataset.data_fingerprint
        == second_result.manifest.dataset.data_fingerprint
    )


@pytest.mark.asyncio
async def test_ai_backtest_preserves_non_signal_skip_reasons() -> None:
    strategy = AiBarJudgeStrategy(
        account_id="paper_account_001",
        lookback_bars=2,
        min_confidence=Decimal("0.60"),
        provider=HoldOnlyAiProvider(),
        suppress_provider_errors=False,
    )
    runner = build_default_backtest_runner(
        _settings(),
        strategy=strategy,
        initial_cash=Decimal("100000"),
        slippage_bps=Decimal("5"),
    )
    bars = (
        _bar_event(close=Decimal("39.50")),
        _bar_event(event_time=BASE_TIME + timedelta(minutes=15), close=Decimal("39.52")),
    )

    result = await runner.run(bars)

    assert result.decisions[0].skip_reason == "ai_lookback_warmup"
    assert result.decisions[0].reason_summary is not None
    assert "1/2 bars collected" in result.decisions[0].reason_summary
    assert result.decisions[1].skip_reason == "ai_decision_hold"
    assert result.decisions[1].reason_summary == "market regime is mixed"
