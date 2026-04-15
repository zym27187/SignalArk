"""Rule-based research strategies for configurable backtests."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from src.domain.events import BarEvent
from src.domain.strategy.audit import StrategyDecisionAudit, build_strategy_decision_audit_summary
from src.domain.strategy.signal import Signal, SignalType

MOVING_AVERAGE_BAND_V1 = "moving_average_band_v1"
DECIMAL_QUANTUM = Decimal("0.0001")


class StrategyContext(Protocol):
    """Minimal runtime context required by backtest-compatible strategies."""

    @property
    def trader_run_uuid(self) -> UUID: ...

    @property
    def received_at(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class RuleBasedNonSignalDecision:
    """Structured audit kept even when the rule strategy does not emit a signal."""

    audit: StrategyDecisionAudit
    skip_reason: str


@dataclass(slots=True)
class _MovingAverageBandState:
    history: deque[Decimal]
    desired_target_position: Decimal = Decimal("0")
    entry_trade_date: date | None = None


def _format_decimal(value: Decimal) -> str:
    return str(value.quantize(DECIMAL_QUANTUM))


class MovingAverageBandStrategy:
    """Long-only moving-average band strategy for research rule backtests."""

    def __init__(
        self,
        *,
        account_id: str,
        strategy_id: str = MOVING_AVERAGE_BAND_V1,
        ma_window: int = 60,
        buy_below_ma_pct: Decimal = Decimal("0.05"),
        sell_above_ma_pct: Decimal = Decimal("0.10"),
        target_position: Decimal = Decimal("400"),
        description: str | None = None,
    ) -> None:
        if ma_window < 2:
            raise ValueError("ma_window must be at least 2")
        if buy_below_ma_pct < 0 or buy_below_ma_pct >= 1:
            raise ValueError("buy_below_ma_pct must be within [0, 1)")
        if sell_above_ma_pct < 0 or sell_above_ma_pct >= 1:
            raise ValueError("sell_above_ma_pct must be within [0, 1)")
        if target_position <= 0:
            raise ValueError("target_position must be positive")

        self._account_id = account_id
        self._strategy_id = strategy_id
        self._ma_window = ma_window
        self._buy_below_ma_pct = buy_below_ma_pct
        self._sell_above_ma_pct = sell_above_ma_pct
        self._target_position = target_position
        self._description = (
            description
            or "Long-only moving-average band strategy against the current daily close."
        )
        self._states: dict[str, _MovingAverageBandState] = defaultdict(self._build_symbol_state)
        self._latest_audit: dict[str, StrategyDecisionAudit] = {}
        self._latest_non_signal_decisions: dict[str, RuleBasedNonSignalDecision] = {}

    async def on_bar(self, event: BarEvent, context: StrategyContext) -> Signal | None:
        if not event.actionable:
            return None

        state = self._states[event.symbol]
        state.history.append(event.close)
        history = tuple(state.history)

        if len(history) < self._ma_window:
            self._latest_non_signal_decisions[event.bar_key] = self._build_warmup_non_signal(
                event=event,
                observed_bars=len(history),
            )
            return None

        moving_average = sum(history, start=Decimal("0")) / Decimal(str(self._ma_window))
        buy_trigger = moving_average * (Decimal("1") - self._buy_below_ma_pct)
        sell_trigger = moving_average * (Decimal("1") + self._sell_above_ma_pct)
        deviation_ratio = (event.close - moving_average) / moving_average

        if state.desired_target_position <= 0 and event.close <= buy_trigger:
            signal = self._build_signal(
                event=event,
                context=context,
                signal_type=SignalType.ENTRY,
                target_position=self._target_position,
                reason_summary=(
                    f"close {event.close} <= buy_trigger {buy_trigger}; "
                    f"ma{self._ma_window} {moving_average}; "
                    f"deviation_pct {_format_decimal(deviation_ratio * Decimal('100'))}; "
                    f"rebalance to {self._target_position}"
                ),
            )
            state.desired_target_position = self._target_position
            state.entry_trade_date = (
                None if event.market_state is None else event.market_state.trade_date
            )
            self._remember_signal_audit(
                event=event,
                signal=signal,
                moving_average=moving_average,
                buy_trigger=buy_trigger,
                sell_trigger=sell_trigger,
                deviation_ratio=deviation_ratio,
                position_state="entry",
            )
            return signal

        if (
            state.desired_target_position > 0
            and event.market_state is not None
            and state.entry_trade_date == event.market_state.trade_date
        ):
            self._latest_non_signal_decisions[event.bar_key] = (
                self._build_t_plus_one_non_signal(
                    event=event,
                    moving_average=moving_average,
                    buy_trigger=buy_trigger,
                    sell_trigger=sell_trigger,
                    deviation_ratio=deviation_ratio,
                )
            )
            return None

        if state.desired_target_position > 0 and event.close >= sell_trigger:
            signal = self._build_signal(
                event=event,
                context=context,
                signal_type=SignalType.EXIT,
                target_position=Decimal("0"),
                reason_summary=(
                    f"close {event.close} >= sell_trigger {sell_trigger}; "
                    f"ma{self._ma_window} {moving_average}; "
                    f"deviation_pct {_format_decimal(deviation_ratio * Decimal('100'))}; "
                    "flatten position"
                ),
            )
            state.desired_target_position = Decimal("0")
            state.entry_trade_date = None
            self._remember_signal_audit(
                event=event,
                signal=signal,
                moving_average=moving_average,
                buy_trigger=buy_trigger,
                sell_trigger=sell_trigger,
                deviation_ratio=deviation_ratio,
                position_state="exit",
            )
            return signal

        self._latest_non_signal_decisions[event.bar_key] = self._build_hold_non_signal(
            event=event,
            moving_average=moving_average,
            buy_trigger=buy_trigger,
            sell_trigger=sell_trigger,
            deviation_ratio=deviation_ratio,
            in_position=state.desired_target_position > 0,
        )
        return None

    def build_non_signal_decision(self, event: BarEvent) -> RuleBasedNonSignalDecision | None:
        return self._latest_non_signal_decisions.get(event.bar_key)

    def build_decision_audit(self, event: BarEvent, signal: Signal) -> StrategyDecisionAudit:
        return self._latest_audit.get(
            event.bar_key,
            StrategyDecisionAudit(
                input_snapshot={},
                signal_snapshot={},
                reason_summary=signal.reason_summary or "",
                summary=self._build_audit_summary(
                    decision=signal.signal_type.value,
                    reason_summary=signal.reason_summary or "",
                ),
            ),
        )

    def backtest_metadata(self) -> dict[str, object]:
        return {
            "strategy_id": self._strategy_id,
            "description": self._description,
            "parameters": {
                "rule_template": self._strategy_id,
                "timeframe": "1d",
                "ma_window": str(self._ma_window),
                "buy_below_ma_pct": str(self._buy_below_ma_pct),
                "sell_above_ma_pct": str(self._sell_above_ma_pct),
                "target_position": str(self._target_position),
            },
        }

    def _build_symbol_state(self) -> _MovingAverageBandState:
        return _MovingAverageBandState(history=deque(maxlen=self._ma_window))

    def _build_signal(
        self,
        *,
        event: BarEvent,
        context: StrategyContext,
        signal_type: SignalType,
        target_position: Decimal,
        reason_summary: str,
    ) -> Signal:
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
            created_at=max(context.received_at, event.event_time),
            reason_summary=reason_summary,
        )

    def _remember_signal_audit(
        self,
        *,
        event: BarEvent,
        signal: Signal,
        moving_average: Decimal,
        buy_trigger: Decimal,
        sell_trigger: Decimal,
        deviation_ratio: Decimal,
        position_state: str,
    ) -> None:
        self._latest_non_signal_decisions.pop(event.bar_key, None)
        self._latest_audit[event.bar_key] = StrategyDecisionAudit(
            input_snapshot=self._build_input_snapshot(
                event=event,
                moving_average=moving_average,
                buy_trigger=buy_trigger,
                sell_trigger=sell_trigger,
                deviation_ratio=deviation_ratio,
                position_state=position_state,
            ),
            signal_snapshot={
                "signal_id": str(signal.id),
                "signal_type": signal.signal_type.value,
                "target_position": str(signal.target_position),
                "event_time": signal.event_time.isoformat(),
                "created_at": signal.created_at.isoformat(),
            },
            reason_summary=signal.reason_summary or "",
            summary=self._build_audit_summary(
                decision=signal.signal_type.value,
                reason_summary=signal.reason_summary or "",
            ),
        )

    def _build_warmup_non_signal(
        self,
        *,
        event: BarEvent,
        observed_bars: int,
    ) -> RuleBasedNonSignalDecision:
        reason_summary = (
            "Waiting for enough finalized daily bars before the first moving-average-band "
            f"decision ({observed_bars}/{self._ma_window} bars collected)."
        )
        return RuleBasedNonSignalDecision(
            audit=StrategyDecisionAudit(
                input_snapshot={
                    "bar_key": event.bar_key,
                    "close": str(event.close),
                    "ma_window": str(self._ma_window),
                    "observed_bars": str(observed_bars),
                    "timeframe": event.timeframe,
                },
                signal_snapshot={},
                reason_summary=reason_summary,
                summary=self._build_audit_summary(
                    decision="hold",
                    reason_summary=reason_summary,
                ),
            ),
            skip_reason="moving_average_band_warmup",
        )

    def _build_t_plus_one_non_signal(
        self,
        *,
        event: BarEvent,
        moving_average: Decimal,
        buy_trigger: Decimal,
        sell_trigger: Decimal,
        deviation_ratio: Decimal,
    ) -> RuleBasedNonSignalDecision:
        reason_summary = (
            f"close {event.close} reached sell-ready territory around ma{self._ma_window} "
            f"{moving_average}, but A-share T+1 keeps the same-day inventory unsellable."
        )
        return RuleBasedNonSignalDecision(
            audit=StrategyDecisionAudit(
                input_snapshot=self._build_input_snapshot(
                    event=event,
                    moving_average=moving_average,
                    buy_trigger=buy_trigger,
                    sell_trigger=sell_trigger,
                    deviation_ratio=deviation_ratio,
                    position_state="t_plus_one_locked",
                ),
                signal_snapshot={},
                reason_summary=reason_summary,
                summary=self._build_audit_summary(
                    decision="hold",
                    reason_summary=reason_summary,
                ),
            ),
            skip_reason="moving_average_band_t_plus_one_locked",
        )

    def _build_hold_non_signal(
        self,
        *,
        event: BarEvent,
        moving_average: Decimal,
        buy_trigger: Decimal,
        sell_trigger: Decimal,
        deviation_ratio: Decimal,
        in_position: bool,
    ) -> RuleBasedNonSignalDecision:
        reason_summary = (
            (
                f"close {event.close} stayed below sell_trigger {sell_trigger} around "
                f"ma{self._ma_window} {moving_average}; keep holding"
            )
            if in_position
            else (
                f"close {event.close} stayed above buy_trigger {buy_trigger} around "
                f"ma{self._ma_window} {moving_average}; keep waiting"
            )
        )
        return RuleBasedNonSignalDecision(
            audit=StrategyDecisionAudit(
                input_snapshot=self._build_input_snapshot(
                    event=event,
                    moving_average=moving_average,
                    buy_trigger=buy_trigger,
                    sell_trigger=sell_trigger,
                    deviation_ratio=deviation_ratio,
                    position_state="holding" if in_position else "flat",
                ),
                signal_snapshot={},
                reason_summary=reason_summary,
                summary=self._build_audit_summary(
                    decision="hold",
                    reason_summary=reason_summary,
                ),
            ),
            skip_reason=(
                "moving_average_band_sell_threshold_not_met"
                if in_position
                else "moving_average_band_buy_threshold_not_met"
            ),
        )

    def _build_input_snapshot(
        self,
        *,
        event: BarEvent,
        moving_average: Decimal,
        buy_trigger: Decimal,
        sell_trigger: Decimal,
        deviation_ratio: Decimal,
        position_state: str,
    ) -> dict[str, str | None]:
        trade_date = (
            None
            if event.market_state is None
            else event.market_state.trade_date.isoformat()
        )
        return {
            "bar_key": event.bar_key,
            "timeframe": event.timeframe,
            "trade_date": trade_date,
            "close": str(event.close),
            "ma_window": str(self._ma_window),
            "moving_average": _format_decimal(moving_average),
            "buy_trigger": _format_decimal(buy_trigger),
            "sell_trigger": _format_decimal(sell_trigger),
            "deviation_pct": _format_decimal(deviation_ratio * Decimal("100")),
            "position_state": position_state,
            "target_position": str(self._target_position),
        }

    def _build_audit_summary(
        self,
        *,
        decision: str,
        reason_summary: str,
    ):
        return build_strategy_decision_audit_summary(
            provider_id="deterministic_policy",
            model_or_policy_version=self._strategy_id,
            decision=decision,
            confidence=None,
            reason_summary=reason_summary,
        )
