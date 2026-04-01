"""Baseline strategy implementations used by the trader runtime."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from src.domain.events import BarEvent
from src.domain.strategy.signal import Signal, SignalType

BASELINE_MOMENTUM_V1 = "baseline_momentum_v1"


class StrategyContext(Protocol):
    """Minimal runtime context required by the baseline strategy."""

    @property
    def trader_run_uuid(self) -> UUID: ...

    @property
    def received_at(self) -> datetime: ...


class BaselineMomentumStrategy:
    """A minimal long-only strategy that compares close to previous close."""

    def __init__(
        self,
        *,
        account_id: str,
        strategy_id: str = BASELINE_MOMENTUM_V1,
        target_position: Decimal = Decimal("400"),
    ) -> None:
        if target_position <= 0:
            raise ValueError("target_position must be positive for baseline momentum strategy")

        self._account_id = account_id
        self._strategy_id = strategy_id
        self._target_position = target_position

    async def on_bar(self, event: BarEvent, context: StrategyContext) -> Signal | None:
        market_state = event.market_state
        if market_state is None or market_state.previous_close <= 0:
            return None

        bullish = event.close > market_state.previous_close
        target_position = self._target_position if bullish else Decimal("0")
        signal_type = SignalType.REBALANCE if bullish else SignalType.EXIT
        close_vs_previous_close = (
            f"close {event.close} {'>' if bullish else '<='} "
            f"previous_close {market_state.previous_close}"
        )
        reason_summary = (
            f"{close_vs_previous_close}; target {target_position}"
            if bullish
            else f"{close_vs_previous_close}; flatten"
        )

        return Signal(
            strategy_id=self._strategy_id,
            trader_run_id=context.trader_run_uuid,
            account_id=self._account_id,
            exchange=event.exchange,
            symbol=event.symbol,
            timeframe=event.timeframe,
            signal_type=signal_type,
            target_position=target_position,
            event_time=event.event_time,
            created_at=context.received_at,
            reason_summary=reason_summary,
        )


def build_strategy(*, strategy_id: str, account_id: str) -> BaselineMomentumStrategy:
    """Resolve the configured primary strategy into a runtime implementation."""

    normalized_strategy_id = strategy_id.strip()
    if normalized_strategy_id == BASELINE_MOMENTUM_V1:
        return BaselineMomentumStrategy(
            account_id=account_id,
            strategy_id=normalized_strategy_id,
        )
    raise ValueError(f"Unsupported primary strategy: {strategy_id}")
