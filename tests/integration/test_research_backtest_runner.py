from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from apps.research import build_default_backtest_runner
from src.config import Settings
from src.domain.events import BarEvent
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase

SHANGHAI = ZoneInfo("Asia/Shanghai")
DAY_ONE = datetime(2026, 4, 1, 14, 0, tzinfo=SHANGHAI)
DAY_TWO = datetime(2026, 4, 2, 14, 0, tzinfo=SHANGHAI)


def _settings() -> Settings:
    return Settings(postgres_dsn="sqlite+pysqlite:///:memory:")


def _market_state(*, trade_date: date, previous_close: Decimal) -> MarketStateSnapshot:
    upper_limit = (previous_close * Decimal("1.10")).quantize(Decimal("0.01"))
    lower_limit = (previous_close * Decimal("0.90")).quantize(Decimal("0.01"))
    return MarketStateSnapshot(
        trade_date=trade_date,
        previous_close=previous_close,
        upper_limit_price=upper_limit,
        lower_limit_price=lower_limit,
        trading_phase=TradingPhase.CONTINUOUS_AUCTION,
        suspension_status=SuspensionStatus.ACTIVE,
    )


def _bar_event(
    *,
    event_time: datetime,
    close: Decimal,
    previous_close: Decimal,
) -> BarEvent:
    return BarEvent(
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        bar_start_time=event_time - timedelta(minutes=15),
        bar_end_time=event_time,
        event_time=event_time,
        ingest_time=event_time + timedelta(seconds=2),
        open=previous_close,
        high=max(close, previous_close),
        low=min(close, previous_close),
        close=close,
        volume=Decimal("1000"),
        closed=True,
        final=True,
        source_kind="historical",
        market_state=_market_state(
            trade_date=event_time.date(),
            previous_close=previous_close,
        ),
    )


@pytest.mark.asyncio
async def test_research_backtest_runner_executes_minimal_event_driven_flow_with_t_plus_one(
) -> None:
    runner = build_default_backtest_runner(
        _settings(),
        initial_cash=Decimal("100000"),
        slippage_bps=Decimal("5"),
    )
    bars = (
        _bar_event(
            event_time=DAY_ONE,
            close=Decimal("39.48"),
            previous_close=Decimal("39.47"),
        ),
        _bar_event(
            event_time=DAY_ONE + timedelta(minutes=15),
            close=Decimal("39.49"),
            previous_close=Decimal("39.47"),
        ),
        _bar_event(
            event_time=DAY_ONE + timedelta(minutes=30),
            close=Decimal("39.50"),
            previous_close=Decimal("39.47"),
        ),
        _bar_event(
            event_time=DAY_ONE + timedelta(minutes=45),
            close=Decimal("39.52"),
            previous_close=Decimal("39.47"),
        ),
        _bar_event(
            event_time=DAY_TWO,
            close=Decimal("39.10"),
            previous_close=Decimal("39.52"),
        ),
    )

    result = await runner.run(bars)

    assert len(result.decisions) == 5
    assert result.decisions[0].skip_reason == "baseline_trend_warmup"
    assert result.decisions[1].skip_reason == "baseline_trend_warmup"
    assert result.decisions[2].order_plan["side"] == "BUY"
    assert result.decisions[2].signal is not None
    assert result.decisions[2].signal.target_position == Decimal("200")
    assert result.decisions[3].order_plan["side"] == "BUY"
    assert result.decisions[3].signal is not None
    assert result.decisions[3].signal.target_position == Decimal("400")
    assert result.decisions[4].order_plan["side"] == "SELL"
    assert result.decisions[4].reason_summary is not None
    assert "trailing_stop" in result.decisions[4].reason_summary

    assert result.performance.signal_count == 3
    assert result.performance.order_count == 3
    assert result.performance.trade_count == 3
    assert result.performance.fill_count == 3
    assert result.performance.sharpe_ratio is not None
    assert result.performance.return_to_drawdown_ratio is not None
    assert result.performance.avg_holding_bars == Decimal("1.5000")
    assert result.performance.avg_trade_pnl is not None
    assert result.performance.avg_losing_trade_pnl is not None

    assert result.fill_events[0].fill.price == Decimal("39.52")
    assert result.fill_events[0].fill.qty == Decimal("200")
    assert result.fill_events[1].fill.price == Decimal("39.54")
    assert result.fill_events[1].fill.qty == Decimal("200")
    assert result.fill_events[2].fill.price == Decimal("39.08")
    assert result.fill_events[2].fill.qty == Decimal("400")

    final_position = result.positions["600036.SH"]
    assert final_position.qty == Decimal("0")
    assert final_position.sellable_qty == Decimal("0")

    assert result.manifest.strategy.strategy_id == "baseline_momentum_v1"
    assert result.manifest.cost_assumptions.slippage_bps == Decimal("5")
    assert result.manifest.dataset.bar_count == 5
    assert result.manifest.strategy.parameters["exit_threshold_pct"] is not None
