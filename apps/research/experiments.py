"""Batch research helpers for parameter sweeps and rolling evaluations."""

from __future__ import annotations

import json
from decimal import Decimal
from itertools import product
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from src.config import Settings
from src.domain.events import BarEvent
from src.domain.strategy import (
    BASELINE_MOMENTUM_V1,
    BaselineMomentumConfig,
    BaselineMomentumStrategy,
    load_baseline_momentum_config,
)
from src.services.backtest import BacktestPerformanceSummary
from src.shared.types import DomainModel, NonEmptyStr, ShanghaiDateTime, shanghai_now

from apps.research import build_default_backtest_runner

MAX_SWEEP_COMBINATIONS = 64


class ResearchVariantSummary(DomainModel):
    """Comparable summary for one strategy variant run."""

    label: NonEmptyStr
    strategy_id: NonEmptyStr
    handler_name: NonEmptyStr
    parameters: dict[str, str] = Field(default_factory=dict)
    performance: BacktestPerformanceSummary
    manifest_fingerprint: NonEmptyStr


class ResearchParameterSweepReport(DomainModel):
    """Comparable summary for one baseline parameter sweep."""

    strategy_id: NonEmptyStr = BASELINE_MOMENTUM_V1
    combination_count: int = Field(ge=0)
    ranking_metric: NonEmptyStr = "sharpe_ratio_then_net_pnl"
    best_variant_label: str | None = None
    variants: tuple[ResearchVariantSummary, ...] = ()


class WalkForwardWindowSummary(DomainModel):
    """Summary for one rolling time window."""

    label: NonEmptyStr
    start_time: ShanghaiDateTime
    end_time: ShanghaiDateTime
    bar_count: int = Field(ge=1)
    performance: BacktestPerformanceSummary
    manifest_fingerprint: NonEmptyStr


class ResearchWalkForwardReport(DomainModel):
    """Rolling evaluation report over chronological windows."""

    method: NonEmptyStr = "rolling_window_evaluation"
    strategy_id: NonEmptyStr = BASELINE_MOMENTUM_V1
    window_bars: int = Field(ge=2)
    step_bars: int = Field(ge=1)
    window_count: int = Field(ge=0)
    best_window_label: str | None = None
    windows: tuple[WalkForwardWindowSummary, ...] = ()


class ResearchExperimentReport(DomainModel):
    """Top-level experiment output emitted by the research CLI."""

    generated_at: ShanghaiDateTime = Field(default_factory=shanghai_now)
    dataset_bar_count: int = Field(ge=1)
    parameter_sweep: ResearchParameterSweepReport | None = None
    walk_forward: ResearchWalkForwardReport | None = None


def load_baseline_sweep_grid(path: Path) -> dict[str, list[object]]:
    """Load a baseline parameter grid from JSON or YAML."""

    suffix = path.suffix.lower()
    raw_payload: object
    if suffix == ".json":
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    elif suffix in {".yaml", ".yml"}:
        raw_payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        raise ValueError("baseline sweep grid must be JSON or YAML")

    if not isinstance(raw_payload, dict):
        raise TypeError("baseline sweep grid must contain an object at the top level")

    normalized_grid: dict[str, list[object]] = {}
    for raw_key, raw_values in raw_payload.items():
        key = str(raw_key).strip()
        if not key:
            raise ValueError("baseline sweep grid keys must be non-empty")
        if not isinstance(raw_values, list) or not raw_values:
            raise ValueError(f"baseline sweep grid field {key} must contain a non-empty list")
        normalized_grid[key] = list(raw_values)

    return normalized_grid


async def run_baseline_parameter_sweep(
    *,
    settings: Settings,
    bars: list[BarEvent],
    parameter_grid: dict[str, list[object]],
    initial_cash,
    slippage_bps,
    slippage_model: str,
) -> ResearchParameterSweepReport:
    """Run a baseline strategy sweep over a small parameter grid."""

    base_config = load_baseline_momentum_config(BASELINE_MOMENTUM_V1)
    normalized_configs = _expand_baseline_configs(base_config, parameter_grid)
    variants: list[ResearchVariantSummary] = []

    for index, config in enumerate(normalized_configs, start=1):
        strategy = _build_baseline_strategy(
            account_id=settings.account_id,
            config=config,
        )
        result = await build_default_backtest_runner(
            settings,
            strategy=strategy,
            initial_cash=initial_cash,
            slippage_bps=slippage_bps,
            slippage_model=slippage_model,
        ).run(bars)
        variants.append(
            ResearchVariantSummary(
                label=f"variant_{index:03d}",
                strategy_id=result.manifest.strategy.strategy_id,
                handler_name=result.manifest.strategy.handler_name,
                parameters=_serialize_strategy_parameters(config),
                performance=result.performance,
                manifest_fingerprint=result.manifest.manifest_fingerprint,
            )
        )

    ranked_variants = tuple(sorted(variants, key=_variant_sort_key, reverse=True))
    return ResearchParameterSweepReport(
        combination_count=len(ranked_variants),
        best_variant_label=None if not ranked_variants else ranked_variants[0].label,
        variants=ranked_variants,
    )


async def run_walk_forward_evaluation(
    *,
    settings: Settings,
    bars: list[BarEvent],
    window_bars: int,
    step_bars: int | None,
    initial_cash,
    slippage_bps,
    slippage_model: str,
) -> ResearchWalkForwardReport:
    """Run a rolling evaluation over fixed-size chronological windows."""

    if window_bars < 2:
        raise ValueError("walk-forward window_bars must be at least 2")

    resolved_step_bars = window_bars if step_bars is None else step_bars
    if resolved_step_bars < 1:
        raise ValueError("walk-forward step_bars must be positive")

    windows: list[WalkForwardWindowSummary] = []
    if len(bars) < window_bars:
        raise ValueError("walk-forward window_bars cannot exceed the available bar count")

    for index, window_bars_slice in enumerate(
        _rolling_windows(bars, window_bars=window_bars, step_bars=resolved_step_bars),
        start=1,
    ):
        result = await build_default_backtest_runner(
            settings,
            initial_cash=initial_cash,
            slippage_bps=slippage_bps,
            slippage_model=slippage_model,
        ).run(window_bars_slice)
        windows.append(
            WalkForwardWindowSummary(
                label=f"window_{index:03d}",
                start_time=window_bars_slice[0].bar_start_time,
                end_time=window_bars_slice[-1].bar_end_time,
                bar_count=len(window_bars_slice),
                performance=result.performance,
                manifest_fingerprint=result.manifest.manifest_fingerprint,
            )
        )

    ranked_windows = sorted(windows, key=_walk_forward_sort_key, reverse=True)
    return ResearchWalkForwardReport(
        window_bars=window_bars,
        step_bars=resolved_step_bars,
        window_count=len(windows),
        best_window_label=None if not ranked_windows else ranked_windows[0].label,
        windows=tuple(windows),
    )


def _expand_baseline_configs(
    base_config: BaselineMomentumConfig,
    parameter_grid: dict[str, list[object]],
) -> tuple[BaselineMomentumConfig, ...]:
    keys = list(parameter_grid.keys())
    combinations = list(product(*(parameter_grid[key] for key in keys)))
    if len(combinations) > MAX_SWEEP_COMBINATIONS:
        raise ValueError(
            f"baseline sweep generated {len(combinations)} combinations; "
            f"limit is {MAX_SWEEP_COMBINATIONS}"
        )

    base_payload = base_config.model_dump(mode="python")
    configs: list[BaselineMomentumConfig] = []
    for combination in combinations:
        override_payload = dict(zip(keys, combination, strict=True))
        configs.append(BaselineMomentumConfig.model_validate({**base_payload, **override_payload}))
    return tuple(configs)


def _build_baseline_strategy(
    *,
    account_id: str,
    config: BaselineMomentumConfig,
) -> BaselineMomentumStrategy:
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


def _serialize_strategy_parameters(config: BaselineMomentumConfig) -> dict[str, str]:
    payload = config.model_dump(mode="json")
    return {
        str(key): str(value)
        for key, value in payload.items()
        if key not in {"strategy_id", "description"}
    }


def _variant_sort_key(variant: ResearchVariantSummary) -> tuple[Any, ...]:
    sharpe_ratio = variant.performance.sharpe_ratio
    sharpe_sort = Decimal("-999999") if sharpe_ratio is None else sharpe_ratio
    return (
        sharpe_sort,
        variant.performance.net_pnl,
        variant.performance.total_return_pct,
    )


def _walk_forward_sort_key(window: WalkForwardWindowSummary) -> tuple[Any, ...]:
    sharpe_ratio = window.performance.sharpe_ratio
    sharpe_sort = Decimal("-999999") if sharpe_ratio is None else sharpe_ratio
    return (
        sharpe_sort,
        window.performance.net_pnl,
        window.performance.total_return_pct,
    )


def _rolling_windows(
    bars: list[BarEvent],
    *,
    window_bars: int,
    step_bars: int,
) -> tuple[list[BarEvent], ...]:
    windows: list[list[BarEvent]] = []
    for start_index in range(0, len(bars) - window_bars + 1, step_bars):
        windows.append(list(bars[start_index : start_index + window_bars]))
    return tuple(windows)
