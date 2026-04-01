"""Baseline strategy implementations used by the trader runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field

from src.domain.events import BarEvent
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


@dataclass(frozen=True, slots=True)
class StrategyDecisionAudit:
    """Structured audit data for the latest strategy decision."""

    input_snapshot: dict[str, str | None]
    signal_snapshot: dict[str, str]
    reason_summary: str


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


class BaselineMomentumStrategy:
    """A minimal long-only strategy using threshold momentum vs previous close."""

    def __init__(
        self,
        *,
        account_id: str,
        strategy_id: str = BASELINE_MOMENTUM_V1,
        target_position: Decimal = Decimal("400"),
        entry_threshold_pct: Decimal = Decimal("0.0005"),
        description: str | None = None,
    ) -> None:
        if target_position <= 0:
            raise ValueError("target_position must be positive for baseline momentum strategy")
        if entry_threshold_pct < 0 or entry_threshold_pct >= 1:
            raise ValueError("entry_threshold_pct must be within [0, 1)")

        self._account_id = account_id
        self._strategy_id = strategy_id
        self._target_position = target_position
        self._entry_threshold_pct = entry_threshold_pct
        self._description = description or "Long-only threshold momentum against previous close."

    async def on_bar(self, event: BarEvent, context: StrategyContext) -> Signal | None:
        market_state = event.market_state
        if market_state is None or market_state.previous_close <= 0:
            return None

        momentum_ratio = (event.close - market_state.previous_close) / market_state.previous_close
        bullish = momentum_ratio >= self._entry_threshold_pct
        target_position = self._target_position if bullish else Decimal("0")
        signal_type = SignalType.REBALANCE if bullish else SignalType.EXIT
        comparison = ">=" if bullish else "<"
        reason_summary = (
            f"close {event.close} vs previous_close {market_state.previous_close}; "
            f"momentum_pct {_format_pct(momentum_ratio)} {comparison} "
            f"threshold_pct {_format_pct(self._entry_threshold_pct)}; "
            f"{'rebalance to ' + str(target_position) if bullish else 'flatten'}"
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

    def build_decision_audit(self, event: BarEvent, signal: Signal) -> StrategyDecisionAudit:
        """Build the structured input/output snapshot for one signal decision."""

        market_state = event.market_state
        momentum_ratio = Decimal("0")
        if market_state is not None:
            momentum_ratio = (
                event.close - market_state.previous_close
            ) / market_state.previous_close

        input_snapshot = {
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
            "entry_threshold_pct": _format_pct(self._entry_threshold_pct),
        }
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
        )


def build_strategy(*, strategy_id: str, account_id: str) -> BaselineMomentumStrategy:
    """Resolve the configured primary strategy into a runtime implementation."""

    normalized_strategy_id = strategy_id.strip()
    if normalized_strategy_id == BASELINE_MOMENTUM_V1:
        config = load_baseline_momentum_config(normalized_strategy_id)
        return BaselineMomentumStrategy(
            account_id=account_id,
            strategy_id=config.strategy_id,
            target_position=config.target_position,
            entry_threshold_pct=config.entry_threshold_pct,
            description=config.description,
        )
    raise ValueError(f"Unsupported primary strategy: {strategy_id}")
