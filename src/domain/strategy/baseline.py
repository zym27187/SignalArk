"""Baseline strategy implementations used by the trader runtime."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.events import BarEvent
from src.domain.strategy.ai import AI_BAR_JUDGE_V1, build_ai_bar_judge_strategy
from src.domain.strategy.audit import StrategyDecisionAudit, build_strategy_decision_audit_summary
from src.domain.strategy.signal import Signal, SignalType

BASELINE_MOMENTUM_V1 = "baseline_momentum_v1"
ROOT_DIR = Path(__file__).resolve().parents[3]
STRATEGY_CONFIG_DIR = ROOT_DIR / "configs" / "strategies"
PERCENT_DISPLAY_QUANTUM = Decimal("0.0001")


class StrategyContext(Protocol):
    """Minimal runtime context required by the baseline strategy."""

    @property
    def trader_run_uuid(self) -> UUID: ...

    @property
    def received_at(self) -> datetime: ...


class BaselineMomentumConfig(BaseModel):
    """File-backed parameters for the baseline threshold-momentum strategy."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    strategy_id: str = BASELINE_MOMENTUM_V1
    description: str = "Long-only threshold momentum against previous close."
    target_position: Decimal = Field(gt=Decimal("0"))
    entry_threshold_pct: Decimal = Field(ge=Decimal("0"), lt=Decimal("1"))
    exit_threshold_pct: Decimal = Field(gt=Decimal("-1"), lt=Decimal("1"))
    trend_lookback_bars: int = Field(ge=2, le=32)
    min_trend_up_bars: int = Field(ge=1)
    strong_entry_threshold_pct: Decimal = Field(ge=Decimal("0"), lt=Decimal("1"))
    reduced_target_ratio: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    trailing_stop_pct: Decimal = Field(gt=Decimal("0"), lt=Decimal("1"))

    @model_validator(mode="after")
    def validate_thresholds(self) -> BaselineMomentumConfig:
        if self.exit_threshold_pct > self.entry_threshold_pct:
            raise ValueError("exit_threshold_pct cannot exceed entry_threshold_pct")
        if self.strong_entry_threshold_pct < self.entry_threshold_pct:
            raise ValueError("strong_entry_threshold_pct cannot be below entry_threshold_pct")
        if self.min_trend_up_bars > self.trend_lookback_bars - 1:
            raise ValueError(
                "min_trend_up_bars cannot exceed trend_lookback_bars - 1 for close-to-close checks"
            )
        return self


def _config_path(strategy_id: str) -> Path:
    return STRATEGY_CONFIG_DIR / f"{strategy_id}.yaml"


@lru_cache(maxsize=8)
def load_baseline_momentum_config(strategy_id: str) -> BaselineMomentumConfig:
    """Load the repo-local baseline strategy parameters for one strategy id."""

    normalized_strategy_id = strategy_id.strip()
    path = _config_path(normalized_strategy_id)
    if not path.exists():
        raise FileNotFoundError(f"Strategy config does not exist: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Strategy config must contain a mapping at the top level: {path}")

    config = BaselineMomentumConfig.model_validate(payload)
    if config.strategy_id != normalized_strategy_id:
        raise ValueError(
            "Strategy config id does not match the requested strategy id: "
            f"{config.strategy_id} != {normalized_strategy_id}"
        )
    return config


def _format_pct(ratio: Decimal) -> str:
    return str((ratio * Decimal("100")).quantize(PERCENT_DISPLAY_QUANTUM))


@dataclass(frozen=True, slots=True)
class BaselineNonSignalDecision:
    """Structured audit kept even when the baseline strategy does not emit a signal."""

    audit: StrategyDecisionAudit
    skip_reason: str


@dataclass(slots=True)
class _BaselineSymbolState:
    history: deque[BarEvent]
    desired_target_position: Decimal = Decimal("0")
    entry_reference_price: Decimal | None = None
    peak_close_since_entry: Decimal | None = None


class BaselineMomentumStrategy:
    """A long-only baseline strategy with hysteresis, trend confirmation, and risk exits."""

    def __init__(
        self,
        *,
        account_id: str,
        strategy_id: str = BASELINE_MOMENTUM_V1,
        target_position: Decimal = Decimal("400"),
        entry_threshold_pct: Decimal = Decimal("0.0005"),
        exit_threshold_pct: Decimal = Decimal("0"),
        trend_lookback_bars: int = 3,
        min_trend_up_bars: int = 2,
        strong_entry_threshold_pct: Decimal = Decimal("0.0012"),
        reduced_target_ratio: Decimal = Decimal("0.5"),
        trailing_stop_pct: Decimal = Decimal("0.01"),
        description: str | None = None,
    ) -> None:
        if target_position <= 0:
            raise ValueError("target_position must be positive for baseline momentum strategy")
        if entry_threshold_pct < 0 or entry_threshold_pct >= 1:
            raise ValueError("entry_threshold_pct must be within [0, 1)")
        if exit_threshold_pct <= -1 or exit_threshold_pct >= 1:
            raise ValueError("exit_threshold_pct must be within (-1, 1)")
        if exit_threshold_pct > entry_threshold_pct:
            raise ValueError("exit_threshold_pct cannot exceed entry_threshold_pct")
        if trend_lookback_bars < 2:
            raise ValueError("trend_lookback_bars must be at least 2")
        if min_trend_up_bars < 1 or min_trend_up_bars > trend_lookback_bars - 1:
            raise ValueError(
                "min_trend_up_bars must be within [1, trend_lookback_bars - 1]"
            )
        if strong_entry_threshold_pct < entry_threshold_pct or strong_entry_threshold_pct >= 1:
            raise ValueError(
                "strong_entry_threshold_pct must be within [entry_threshold_pct, 1)"
            )
        if reduced_target_ratio <= 0 or reduced_target_ratio > 1:
            raise ValueError("reduced_target_ratio must be within (0, 1]")
        if trailing_stop_pct <= 0 or trailing_stop_pct >= 1:
            raise ValueError("trailing_stop_pct must be within (0, 1)")

        self._account_id = account_id
        self._strategy_id = strategy_id
        self._target_position = target_position
        self._entry_threshold_pct = entry_threshold_pct
        self._exit_threshold_pct = exit_threshold_pct
        self._trend_lookback_bars = trend_lookback_bars
        self._min_trend_up_bars = min_trend_up_bars
        self._strong_entry_threshold_pct = strong_entry_threshold_pct
        self._reduced_target_ratio = reduced_target_ratio
        self._trailing_stop_pct = trailing_stop_pct
        self._reduced_target_position = target_position * reduced_target_ratio
        self._description = description or "Long-only threshold momentum against previous close."
        self._states: dict[str, _BaselineSymbolState] = defaultdict(self._build_symbol_state)
        self._latest_audit: dict[str, StrategyDecisionAudit] = {}
        self._latest_non_signal_decisions: dict[str, BaselineNonSignalDecision] = {}

    async def on_bar(self, event: BarEvent, context: StrategyContext) -> Signal | None:
        market_state = event.market_state
        if not event.actionable or market_state is None or market_state.previous_close <= 0:
            return None

        state = self._states[event.symbol]
        state.history.append(event)
        history = tuple(state.history)

        momentum_ratio = (event.close - market_state.previous_close) / market_state.previous_close
        if len(history) < self._trend_lookback_bars:
            self._latest_non_signal_decisions[event.bar_key] = (
                self._build_warmup_non_signal_decision(
                    event=event,
                    momentum_ratio=momentum_ratio,
                    observed_bars=len(history),
                )
            )
            return None

        trend_return_ratio = _compute_trend_return(history)
        positive_change_count = _count_positive_close_changes(history)
        trend_confirmed = (
            trend_return_ratio > 0 and positive_change_count >= self._min_trend_up_bars
        )

        if state.desired_target_position > 0:
            state.peak_close_since_entry = max(
                state.peak_close_since_entry or event.close,
                event.close,
            )

        trailing_stop_price = self._resolve_trailing_stop_price(state)
        if state.desired_target_position > 0 and trailing_stop_price is not None:
            if event.close <= trailing_stop_price:
                signal = self._build_signal(
                    event=event,
                    context=context,
                    signal_type=SignalType.EXIT,
                    target_position=Decimal("0"),
                    reason_summary=(
                        f"close {event.close} breached trailing_stop {trailing_stop_price}; "
                        f"peak_close_since_entry {state.peak_close_since_entry}; flatten"
                    ),
                )
                self._remember_signal_audit(
                    event=event,
                    signal=signal,
                    momentum_ratio=momentum_ratio,
                    trend_return_ratio=trend_return_ratio,
                    positive_change_count=positive_change_count,
                    trend_confirmed=trend_confirmed,
                    position_tier="risk_exit",
                    entry_ready=False,
                    trailing_stop_price=trailing_stop_price,
                )
                self._clear_position_state(state)
                return signal

        if state.desired_target_position > 0 and momentum_ratio <= self._exit_threshold_pct:
            signal = self._build_signal(
                event=event,
                context=context,
                signal_type=SignalType.EXIT,
                target_position=Decimal("0"),
                reason_summary=(
                    f"close {event.close} vs previous_close {market_state.previous_close}; "
                    f"momentum_pct {_format_pct(momentum_ratio)} <= "
                    f"exit_threshold_pct {_format_pct(self._exit_threshold_pct)}; flatten"
                ),
            )
            self._remember_signal_audit(
                event=event,
                signal=signal,
                momentum_ratio=momentum_ratio,
                trend_return_ratio=trend_return_ratio,
                positive_change_count=positive_change_count,
                trend_confirmed=trend_confirmed,
                position_tier="exit",
                entry_ready=False,
                trailing_stop_price=trailing_stop_price,
            )
            self._clear_position_state(state)
            return signal

        entry_ready = momentum_ratio >= self._entry_threshold_pct and trend_confirmed
        if entry_ready:
            position_tier = "full"
            target_position = self._target_position
            if momentum_ratio < self._strong_entry_threshold_pct:
                position_tier = "reduced"
                target_position = self._reduced_target_position

            signal = self._build_signal(
                event=event,
                context=context,
                signal_type=SignalType.REBALANCE,
                target_position=target_position,
                reason_summary=(
                    f"close {event.close} vs previous_close {market_state.previous_close}; "
                    f"momentum_pct {_format_pct(momentum_ratio)} >= "
                    f"entry_threshold_pct {_format_pct(self._entry_threshold_pct)}; "
                    f"trend_return_pct {_format_pct(trend_return_ratio)}; "
                    "positive_close_changes "
                    f"{positive_change_count}/{self._trend_lookback_bars - 1}; "
                    f"position_tier {position_tier}; rebalance to {target_position}"
                ),
            )
            self._remember_signal_audit(
                event=event,
                signal=signal,
                momentum_ratio=momentum_ratio,
                trend_return_ratio=trend_return_ratio,
                positive_change_count=positive_change_count,
                trend_confirmed=trend_confirmed,
                position_tier=position_tier,
                entry_ready=True,
                trailing_stop_price=trailing_stop_price,
            )
            self._store_position_state(state, target_position=target_position, close=event.close)
            return signal

        if state.desired_target_position > 0:
            signal = self._build_signal(
                event=event,
                context=context,
                signal_type=SignalType.REBALANCE,
                target_position=state.desired_target_position,
                reason_summary=(
                    f"close {event.close} vs previous_close {market_state.previous_close}; "
                    f"momentum_pct {_format_pct(momentum_ratio)} stayed above "
                    f"exit_threshold_pct {_format_pct(self._exit_threshold_pct)} but below "
                    f"entry_threshold_pct {_format_pct(self._entry_threshold_pct)}; "
                    f"hold current target {state.desired_target_position}"
                ),
            )
            self._remember_signal_audit(
                event=event,
                signal=signal,
                momentum_ratio=momentum_ratio,
                trend_return_ratio=trend_return_ratio,
                positive_change_count=positive_change_count,
                trend_confirmed=trend_confirmed,
                position_tier="hold",
                entry_ready=False,
                trailing_stop_price=trailing_stop_price,
            )
            return signal

        self._latest_non_signal_decisions[event.bar_key] = (
            self._build_entry_blocked_non_signal_decision(
                event=event,
                momentum_ratio=momentum_ratio,
                trend_return_ratio=trend_return_ratio,
                positive_change_count=positive_change_count,
                trend_confirmed=trend_confirmed,
            )
        )
        return None

    def build_non_signal_decision(self, event: BarEvent) -> BaselineNonSignalDecision | None:
        """Expose the latest skipped baseline decision for backtest and research UIs."""

        return self._latest_non_signal_decisions.get(event.bar_key)

    def build_decision_audit(self, event: BarEvent, signal: Signal) -> StrategyDecisionAudit:
        """Build the structured input/output snapshot for one signal decision."""

        audit = self._latest_audit.get(event.bar_key)
        if audit is not None:
            return audit

        market_state = event.market_state
        momentum_ratio = Decimal("0")
        if market_state is not None:
            momentum_ratio = (
                event.close - market_state.previous_close
            ) / market_state.previous_close

        input_snapshot = self._build_input_snapshot(
            event=event,
            momentum_ratio=momentum_ratio,
            trend_return_ratio=Decimal("0"),
            positive_change_count=0,
            trend_confirmed=False,
            position_tier="unknown",
            entry_ready=False,
            trailing_stop_price=None,
        )
        signal_snapshot = {
            "signal_id": str(signal.id),
            "signal_type": signal.signal_type.value,
            "target_position": str(signal.target_position),
            "event_time": signal.event_time.isoformat(),
            "created_at": signal.created_at.isoformat(),
        }
        return StrategyDecisionAudit(
            input_snapshot=input_snapshot,
            signal_snapshot=signal_snapshot,
            reason_summary=signal.reason_summary or "",
            summary=self._build_audit_summary(
                decision=signal.signal_type.value,
                reason_summary=signal.reason_summary or "",
            ),
        )

    def backtest_metadata(self) -> dict[str, object]:
        """Expose reproducible strategy metadata for research/backtest runs."""

        return {
            "strategy_id": self._strategy_id,
            "description": self._description,
            "parameters": {
                "target_position": str(self._target_position),
                "entry_threshold_pct": str(self._entry_threshold_pct),
                "exit_threshold_pct": str(self._exit_threshold_pct),
                "trend_lookback_bars": str(self._trend_lookback_bars),
                "min_trend_up_bars": str(self._min_trend_up_bars),
                "strong_entry_threshold_pct": str(self._strong_entry_threshold_pct),
                "reduced_target_ratio": str(self._reduced_target_ratio),
                "trailing_stop_pct": str(self._trailing_stop_pct),
            },
        }

    def _build_symbol_state(self) -> _BaselineSymbolState:
        return _BaselineSymbolState(history=deque(maxlen=self._trend_lookback_bars))

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
        momentum_ratio: Decimal,
        trend_return_ratio: Decimal,
        positive_change_count: int,
        trend_confirmed: bool,
        position_tier: str,
        entry_ready: bool,
        trailing_stop_price: Decimal | None,
    ) -> None:
        self._latest_non_signal_decisions.pop(event.bar_key, None)
        self._latest_audit[event.bar_key] = StrategyDecisionAudit(
            input_snapshot=self._build_input_snapshot(
                event=event,
                momentum_ratio=momentum_ratio,
                trend_return_ratio=trend_return_ratio,
                positive_change_count=positive_change_count,
                trend_confirmed=trend_confirmed,
                position_tier=position_tier,
                entry_ready=entry_ready,
                trailing_stop_price=trailing_stop_price,
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

    def _build_input_snapshot(
        self,
        *,
        event: BarEvent,
        momentum_ratio: Decimal,
        trend_return_ratio: Decimal,
        positive_change_count: int,
        trend_confirmed: bool,
        position_tier: str,
        entry_ready: bool,
        trailing_stop_price: Decimal | None,
    ) -> dict[str, str | None]:
        market_state = event.market_state
        state = self._states[event.symbol]
        return {
            "strategy_description": self._description,
            "bar_key": event.bar_key,
            "source_kind": event.source_kind,
            "bar_start_time": event.bar_start_time.isoformat(),
            "bar_end_time": event.bar_end_time.isoformat(),
            "trade_date": market_state.trade_date.isoformat() if market_state is not None else None,
            "trading_phase": market_state.trading_phase.value if market_state is not None else None,
            "close": str(event.close),
            "previous_close": (
                str(market_state.previous_close) if market_state is not None else None
            ),
            "momentum_pct": _format_pct(momentum_ratio),
            "trend_return_pct": _format_pct(trend_return_ratio),
            "entry_threshold_pct": _format_pct(self._entry_threshold_pct),
            "exit_threshold_pct": _format_pct(self._exit_threshold_pct),
            "strong_entry_threshold_pct": _format_pct(self._strong_entry_threshold_pct),
            "trailing_stop_pct": _format_pct(self._trailing_stop_pct),
            "trailing_stop_price": (
                None if trailing_stop_price is None else str(trailing_stop_price)
            ),
            "trend_lookback_bars": str(self._trend_lookback_bars),
            "min_trend_up_bars": str(self._min_trend_up_bars),
            "positive_close_changes": str(positive_change_count),
            "trend_confirmed": "true" if trend_confirmed else "false",
            "entry_ready": "true" if entry_ready else "false",
            "position_tier": position_tier,
            "desired_target_position": str(state.desired_target_position),
            "entry_reference_price": (
                None if state.entry_reference_price is None else str(state.entry_reference_price)
            ),
            "peak_close_since_entry": (
                None
                if state.peak_close_since_entry is None
                else str(state.peak_close_since_entry)
            ),
            "reduced_target_position": str(self._reduced_target_position),
            "full_target_position": str(self._target_position),
        }

    def _build_warmup_non_signal_decision(
        self,
        *,
        event: BarEvent,
        momentum_ratio: Decimal,
        observed_bars: int,
    ) -> BaselineNonSignalDecision:
        return BaselineNonSignalDecision(
            audit=StrategyDecisionAudit(
                input_snapshot={
                    **self._build_input_snapshot(
                        event=event,
                        momentum_ratio=momentum_ratio,
                        trend_return_ratio=Decimal("0"),
                        positive_change_count=0,
                        trend_confirmed=False,
                        position_tier="warmup",
                        entry_ready=False,
                        trailing_stop_price=None,
                    ),
                    "trend_lookback_bars_required": str(self._trend_lookback_bars),
                    "trend_lookback_bars_observed": str(observed_bars),
                },
                signal_snapshot={},
                reason_summary=(
                    "Waiting for enough finalized bars before the first confirmed baseline "
                    f"decision ({observed_bars}/{self._trend_lookback_bars} bars collected)."
                ),
                summary=self._build_audit_summary(
                    decision="hold",
                    reason_summary=(
                        "Waiting for enough finalized bars before the first confirmed baseline "
                        f"decision ({observed_bars}/{self._trend_lookback_bars} bars collected)."
                    ),
                ),
            ),
            skip_reason="baseline_trend_warmup",
        )

    def _build_entry_blocked_non_signal_decision(
        self,
        *,
        event: BarEvent,
        momentum_ratio: Decimal,
        trend_return_ratio: Decimal,
        positive_change_count: int,
        trend_confirmed: bool,
    ) -> BaselineNonSignalDecision:
        skip_reason = (
            "baseline_trend_unconfirmed"
            if not trend_confirmed
            else "baseline_entry_threshold_not_met"
        )
        reason_summary = (
            f"close {event.close} vs previous_close {event.market_state.previous_close}; "
            f"momentum_pct {_format_pct(momentum_ratio)} below entry_threshold_pct "
            f"{_format_pct(self._entry_threshold_pct)}; no position change"
            if trend_confirmed
            else (
                f"trend confirmation pending: trend_return_pct {_format_pct(trend_return_ratio)}; "
                f"positive_close_changes {positive_change_count}/{self._trend_lookback_bars - 1}; "
                "skip entry"
            )
        )
        return BaselineNonSignalDecision(
            audit=StrategyDecisionAudit(
                input_snapshot=self._build_input_snapshot(
                    event=event,
                    momentum_ratio=momentum_ratio,
                    trend_return_ratio=trend_return_ratio,
                    positive_change_count=positive_change_count,
                    trend_confirmed=trend_confirmed,
                    position_tier="flat",
                    entry_ready=False,
                    trailing_stop_price=None,
                ),
                signal_snapshot={},
                reason_summary=reason_summary,
                summary=self._build_audit_summary(
                    decision="hold",
                    reason_summary=reason_summary,
                ),
            ),
            skip_reason=skip_reason,
        )

    def _resolve_trailing_stop_price(self, state: _BaselineSymbolState) -> Decimal | None:
        if state.desired_target_position <= 0 or state.peak_close_since_entry is None:
            return None
        return state.peak_close_since_entry * (Decimal("1") - self._trailing_stop_pct)

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

    @staticmethod
    def _store_position_state(
        state: _BaselineSymbolState,
        *,
        target_position: Decimal,
        close: Decimal,
    ) -> None:
        if state.desired_target_position <= 0:
            state.entry_reference_price = close
            state.peak_close_since_entry = close
        else:
            state.peak_close_since_entry = max(state.peak_close_since_entry or close, close)
        state.desired_target_position = target_position

    @staticmethod
    def _clear_position_state(state: _BaselineSymbolState) -> None:
        state.desired_target_position = Decimal("0")
        state.entry_reference_price = None
        state.peak_close_since_entry = None


def build_strategy(*, strategy_id: str, account_id: str) -> object:
    """Resolve the configured primary strategy into a runtime implementation."""

    normalized_strategy_id = strategy_id.strip()
    if normalized_strategy_id == BASELINE_MOMENTUM_V1:
        config = load_baseline_momentum_config(normalized_strategy_id)
        return BaselineMomentumStrategy(
            account_id=account_id,
            strategy_id=config.strategy_id,
            target_position=config.target_position,
            entry_threshold_pct=config.entry_threshold_pct,
            exit_threshold_pct=config.exit_threshold_pct,
            trend_lookback_bars=config.trend_lookback_bars,
            min_trend_up_bars=config.min_trend_up_bars,
            strong_entry_threshold_pct=config.strong_entry_threshold_pct,
            reduced_target_ratio=config.reduced_target_ratio,
            trailing_stop_pct=config.trailing_stop_pct,
            description=config.description,
        )
    if normalized_strategy_id == AI_BAR_JUDGE_V1:
        return build_ai_bar_judge_strategy(
            strategy_id=normalized_strategy_id,
            account_id=account_id,
        )
    raise ValueError(f"Unsupported primary strategy: {strategy_id}")


def _compute_trend_return(history: tuple[BarEvent, ...]) -> Decimal:
    first_close = history[0].close
    if first_close <= 0:
        return Decimal("0")
    return (history[-1].close - first_close) / first_close


def _count_positive_close_changes(history: tuple[BarEvent, ...]) -> int:
    return sum(
        1
        for previous, current in zip(history, history[1:], strict=False)
        if current.close > previous.close
    )
