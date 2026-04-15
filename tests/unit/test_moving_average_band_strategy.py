from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from apps.trader.runtime import TraderRuntimeState
from apps.trader.service import TraderEventContext
from src.domain.events import BarEvent
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.market.state import compute_price_limits
from src.domain.strategy import MOVING_AVERAGE_BAND_V1, MovingAverageBandStrategy, SignalType

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 1, 14, 0, tzinfo=SHANGHAI)


def _context(offset: int = 0) -> TraderEventContext:
    runtime_state = TraderRuntimeState(trader_run_id="11111111-1111-4111-8111-111111111111")
    received_at = BASE_TIME + timedelta(days=offset, seconds=2)
    return TraderEventContext(
        trader_run_id=runtime_state.trader_run_id,
        instance_id=runtime_state.instance_id,
        received_at=received_at,
        runtime_state=runtime_state,
    )


def _market_state(event_time: datetime, previous_close: Decimal) -> MarketStateSnapshot:
    upper_limit_price, lower_limit_price = compute_price_limits(
        previous_close,
        Decimal("0.50"),
        price_tick=Decimal("0.01"),
    )
    return MarketStateSnapshot(
        trade_date=event_time.date(),
        previous_close=previous_close,
        upper_limit_price=upper_limit_price,
        lower_limit_price=lower_limit_price,
        trading_phase=TradingPhase.CONTINUOUS_AUCTION,
        suspension_status=SuspensionStatus.ACTIVE,
    )


def _bar_event(
    *,
    close: Decimal,
    offset: int,
    previous_close: Decimal,
    event_time: datetime | None = None,
) -> BarEvent:
    resolved_event_time = event_time or (BASE_TIME + timedelta(days=offset))
    return BarEvent(
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="1d",
        bar_start_time=resolved_event_time - timedelta(days=1),
        bar_end_time=resolved_event_time,
        event_time=resolved_event_time,
        ingest_time=resolved_event_time + timedelta(seconds=1),
        open=previous_close,
        high=max(close, previous_close),
        low=min(close, previous_close),
        close=close,
        volume=Decimal("1000"),
        closed=True,
        final=True,
        source_kind="historical",
        market_state=_market_state(resolved_event_time, previous_close),
    )


@pytest.mark.asyncio
async def test_moving_average_band_strategy_waits_for_ma_warmup_before_entry() -> None:
    strategy = MovingAverageBandStrategy(
        account_id="paper_account_001",
        ma_window=3,
        buy_below_ma_pct=Decimal("0.05"),
        sell_above_ma_pct=Decimal("0.10"),
        target_position=Decimal("400"),
    )

    first = await strategy.on_bar(
        _bar_event(close=Decimal("100"), previous_close=Decimal("100"), offset=0),
        _context(0),
    )
    second_event = _bar_event(
        close=Decimal("100"),
        previous_close=Decimal("100"),
        offset=1,
    )
    second = await strategy.on_bar(second_event, _context(1))

    assert first is None
    assert second is None

    warmup = strategy.build_non_signal_decision(second_event)
    assert warmup is not None
    assert warmup.skip_reason == "moving_average_band_warmup"
    assert warmup.audit.input_snapshot["ma_window"] == "3"
    assert warmup.audit.input_snapshot["observed_bars"] == "2"


@pytest.mark.asyncio
async def test_moving_average_band_strategy_emits_entry_and_readable_audit_on_buy_signal() -> None:
    strategy = MovingAverageBandStrategy(
        account_id="paper_account_001",
        ma_window=3,
        buy_below_ma_pct=Decimal("0.05"),
        sell_above_ma_pct=Decimal("0.10"),
        target_position=Decimal("400"),
    )

    await strategy.on_bar(
        _bar_event(close=Decimal("100"), previous_close=Decimal("100"), offset=0),
        _context(0),
    )
    await strategy.on_bar(
        _bar_event(close=Decimal("100"), previous_close=Decimal("100"), offset=1),
        _context(1),
    )
    entry_event = _bar_event(
        close=Decimal("80"),
        previous_close=Decimal("100"),
        offset=2,
    )
    entry_signal = await strategy.on_bar(entry_event, _context(2))

    assert entry_signal is not None
    assert entry_signal.strategy_id == MOVING_AVERAGE_BAND_V1
    assert entry_signal.signal_type is SignalType.ENTRY
    assert entry_signal.target_position == Decimal("400")
    assert entry_signal.reason_summary is not None
    assert "buy threshold" in entry_signal.reason_summary
    assert "target_position 400" in entry_signal.reason_summary

    audit = strategy.build_decision_audit(entry_event, entry_signal)
    assert audit.input_snapshot["moving_average"] == "93.3333"
    assert audit.input_snapshot["buy_below_ma_pct"] == "5.0000"
    assert audit.signal_snapshot["signal_type"] == "ENTRY"


@pytest.mark.asyncio
async def test_moving_average_band_strategy_emits_exit_after_rebound_crosses_sell_threshold(
) -> None:
    strategy = MovingAverageBandStrategy(
        account_id="paper_account_001",
        ma_window=3,
        buy_below_ma_pct=Decimal("0.05"),
        sell_above_ma_pct=Decimal("0.10"),
        target_position=Decimal("400"),
    )

    await strategy.on_bar(
        _bar_event(close=Decimal("100"), previous_close=Decimal("100"), offset=0),
        _context(0),
    )
    await strategy.on_bar(
        _bar_event(close=Decimal("100"), previous_close=Decimal("100"), offset=1),
        _context(1),
    )
    await strategy.on_bar(
        _bar_event(close=Decimal("80"), previous_close=Decimal("100"), offset=2),
        _context(2),
    )
    exit_event = _bar_event(
        close=Decimal("120"),
        previous_close=Decimal("80"),
        offset=3,
    )
    exit_signal = await strategy.on_bar(exit_event, _context(3))

    assert exit_signal is not None
    assert exit_signal.signal_type is SignalType.EXIT
    assert exit_signal.target_position == Decimal("0")
    assert exit_signal.reason_summary is not None
    assert "sell threshold" in exit_signal.reason_summary
    assert "flatten position" in exit_signal.reason_summary

    metadata = strategy.backtest_metadata()
    assert metadata["strategy_id"] == MOVING_AVERAGE_BAND_V1
    assert metadata["parameters"]["rule_template"] == MOVING_AVERAGE_BAND_V1
    assert metadata["parameters"]["timeframe"] == "1d"


@pytest.mark.asyncio
async def test_moving_average_band_strategy_keeps_waiting_when_buy_threshold_is_not_met() -> None:
    strategy = MovingAverageBandStrategy(
        account_id="paper_account_001",
        ma_window=3,
        buy_below_ma_pct=Decimal("0.05"),
        sell_above_ma_pct=Decimal("0.10"),
        target_position=Decimal("400"),
    )

    await strategy.on_bar(
        _bar_event(close=Decimal("100"), previous_close=Decimal("100"), offset=0),
        _context(0),
    )
    await strategy.on_bar(
        _bar_event(close=Decimal("100"), previous_close=Decimal("100"), offset=1),
        _context(1),
    )
    hold_event = _bar_event(
        close=Decimal("100"),
        previous_close=Decimal("100"),
        offset=2,
    )
    hold_signal = await strategy.on_bar(hold_event, _context(2))

    assert hold_signal is None

    hold_decision = strategy.build_non_signal_decision(hold_event)
    assert hold_decision is not None
    assert hold_decision.skip_reason == "moving_average_band_buy_threshold_not_met"
    assert "keep waiting" in hold_decision.audit.reason_summary


@pytest.mark.asyncio
async def test_moving_average_band_strategy_respects_t_plus_one_before_exit() -> None:
    strategy = MovingAverageBandStrategy(
        account_id="paper_account_001",
        ma_window=3,
        buy_below_ma_pct=Decimal("0.05"),
        sell_above_ma_pct=Decimal("0.10"),
        target_position=Decimal("400"),
    )

    await strategy.on_bar(
        _bar_event(close=Decimal("100"), previous_close=Decimal("100"), offset=0),
        _context(0),
    )
    await strategy.on_bar(
        _bar_event(close=Decimal("100"), previous_close=Decimal("100"), offset=1),
        _context(1),
    )
    entry_event_time = BASE_TIME + timedelta(days=2)
    await strategy.on_bar(
        _bar_event(
          close=Decimal("80"),
          previous_close=Decimal("100"),
          offset=2,
          event_time=entry_event_time,
        ),
        _context(2),
    )
    locked_exit_event = _bar_event(
        close=Decimal("120"),
        previous_close=Decimal("80"),
        offset=2,
        event_time=entry_event_time + timedelta(hours=1),
    )
    locked_exit_signal = await strategy.on_bar(locked_exit_event, _context(2))

    assert locked_exit_signal is None

    locked_decision = strategy.build_non_signal_decision(locked_exit_event)
    assert locked_decision is not None
    assert locked_decision.skip_reason == "moving_average_band_t_plus_one_locked"
    assert "same-day inventory unsellable" in locked_decision.audit.reason_summary
