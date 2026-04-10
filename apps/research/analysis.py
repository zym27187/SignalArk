"""Helpers for judging research sample credibility and segmented evaluations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from src.domain.events import BarEvent
from src.services.backtest import BacktestPerformanceSummary, BacktestRunResult

ResearchSamplePurpose = Literal["preview", "evaluation"]

DEFAULT_RESEARCH_PREVIEW_LIMIT = 96
DEFAULT_RESEARCH_EVALUATION_LIMIT = 240
DEFAULT_RESEARCH_SEGMENT_COUNT = 3
MIN_BARS_FOR_SEGMENTED_EVALUATION = 12
SEGMENT_REGIME_THRESHOLD = Decimal("0.015")
PERCENT_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class ResearchSegmentAnalysis:
    """Serializable summary for one chronological slice of the input sample."""

    label: str
    market_regime: str
    market_regime_label: str
    start_time: datetime
    end_time: datetime
    bar_count: int
    price_change_pct: Decimal
    performance: BacktestPerformanceSummary


def resolve_sample_bar_limit(
    *,
    sample_purpose: ResearchSamplePurpose,
    requested_limit: int | None,
) -> int:
    if requested_limit is not None:
        return requested_limit
    if sample_purpose == "preview":
        return DEFAULT_RESEARCH_PREVIEW_LIMIT
    return DEFAULT_RESEARCH_EVALUATION_LIMIT


def supports_time_segmentation(
    *,
    sample_purpose: ResearchSamplePurpose,
    actual_bar_count: int,
) -> bool:
    return (
        sample_purpose == "evaluation"
        and actual_bar_count >= MIN_BARS_FOR_SEGMENTED_EVALUATION
    )


def build_sample_metadata(
    *,
    sample_purpose: ResearchSamplePurpose,
    requested_bar_count: int,
    actual_bar_count: int,
) -> dict[str, object]:
    segmentation_enabled = supports_time_segmentation(
        sample_purpose=sample_purpose,
        actual_bar_count=actual_bar_count,
    )
    if sample_purpose == "preview":
        description = "快速预览最近一段样本，只适合看信号和审计，不建议直接下稳定性结论。"
        warning = "当前结果属于快速预览，请结合更长评估样本再判断策略是否稳定。"
    else:
        description = "评估样本会尽量拉长历史区间，并支持按时间分段比较不同阶段表现。"
        warning = None
        if not segmentation_enabled:
            warning = "当前评估样本过短，暂时无法可靠地做时间分段比较。"

    return {
        "purpose": sample_purpose,
        "label": "快速预览" if sample_purpose == "preview" else "评估样本",
        "requestedBarCount": requested_bar_count,
        "actualBarCount": actual_bar_count,
        "supportsTimeSegmentation": segmentation_enabled,
        "segmentCount": DEFAULT_RESEARCH_SEGMENT_COUNT if segmentation_enabled else 0,
        "description": description,
        "warning": warning,
    }


async def build_segment_analyses(
    *,
    bars: Sequence[BarEvent],
    run_backtest: Callable[[Sequence[BarEvent]], Awaitable[BacktestRunResult]],
    sample_purpose: ResearchSamplePurpose,
) -> tuple[ResearchSegmentAnalysis, ...]:
    if not supports_time_segmentation(
        sample_purpose=sample_purpose,
        actual_bar_count=len(bars),
    ):
        return ()

    analyses: list[ResearchSegmentAnalysis] = []
    for index, segment_bars in enumerate(_split_bars(bars, DEFAULT_RESEARCH_SEGMENT_COUNT)):
        if not segment_bars:
            continue
        segment_result = await run_backtest(segment_bars)
        market_regime, market_regime_label = _classify_market_regime(segment_bars)
        analyses.append(
            ResearchSegmentAnalysis(
                label=_build_segment_label(index, DEFAULT_RESEARCH_SEGMENT_COUNT),
                market_regime=market_regime,
                market_regime_label=market_regime_label,
                start_time=segment_bars[0].bar_start_time,
                end_time=segment_bars[-1].bar_end_time,
                bar_count=len(segment_bars),
                price_change_pct=_to_pct(_price_change_ratio(segment_bars)),
                performance=segment_result.performance,
            )
        )
    return tuple(analyses)


def _split_bars(
    bars: Sequence[BarEvent],
    segment_count: int,
) -> tuple[tuple[BarEvent, ...], ...]:
    resolved_segment_count = min(segment_count, len(bars))
    if resolved_segment_count <= 0:
        return ()

    base_size, remainder = divmod(len(bars), resolved_segment_count)
    start_index = 0
    segments: list[tuple[BarEvent, ...]] = []
    for index in range(resolved_segment_count):
        size = base_size + (1 if index < remainder else 0)
        segment = tuple(bars[start_index : start_index + size])
        if segment:
            segments.append(segment)
        start_index += size
    return tuple(segments)


def _build_segment_label(index: int, total: int) -> str:
    if total == 3:
        return ("前段样本", "中段样本", "后段样本")[index]
    return f"阶段 {index + 1}"


def _classify_market_regime(bars: Sequence[BarEvent]) -> tuple[str, str]:
    price_change_ratio = _price_change_ratio(bars)
    if price_change_ratio >= SEGMENT_REGIME_THRESHOLD:
        return "uptrend", "上涨"
    if price_change_ratio <= -SEGMENT_REGIME_THRESHOLD:
        return "downtrend", "下跌"
    return "sideways", "震荡"


def _price_change_ratio(bars: Sequence[BarEvent]) -> Decimal:
    reference_price = bars[0].open
    if reference_price <= 0:
        return Decimal("0")
    return (bars[-1].close - reference_price) / reference_price


def _to_pct(ratio: Decimal) -> Decimal:
    return (ratio * Decimal("100")).quantize(PERCENT_QUANTUM)
