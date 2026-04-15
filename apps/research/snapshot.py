"""Shared serializers for frontend-facing research snapshot payloads."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Literal

from src.domain.events import BarEvent
from src.services.backtest import (
    BacktestDecisionRecord,
    BacktestPerformanceSummary,
    BacktestRunResult,
)
from src.shared.types import shanghai_now

from apps.research.analysis import (
    ResearchMode,
    ResearchSamplePurpose,
    ResearchSegmentAnalysis,
    resolve_sample_purpose,
)
from apps.research.experiments import (
    ResearchParameterSweepReport,
    ResearchWalkForwardReport,
)

ResearchSnapshotSourceMode = Literal["fixture", "imported", "live"]

RESEARCH_MODE_LABELS: dict[ResearchMode, str] = {
    "preview": "快速预览",
    "evaluation": "评估样本",
    "parameter_scan": "参数扫描",
    "walk_forward": "滚动评估",
}


def build_web_snapshot_payload(
    *,
    result: BacktestRunResult,
    bars: Sequence[BarEvent],
    source_label: str,
    source_mode: ResearchSnapshotSourceMode,
    mode: ResearchMode,
    notes: Sequence[str],
    sample: dict[str, Any] | None = None,
    segments: Sequence[ResearchSegmentAnalysis] = (),
    experiments: dict[str, Any] | None = None,
    comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize a backtest result into the research page snapshot contract."""

    dataset = result.manifest.dataset
    strategy = result.manifest.strategy
    cost_assumptions = result.manifest.cost_assumptions
    performance = result.performance
    baseline = float(performance.starting_equity)
    sample_purpose = _resolve_sample_purpose(sample=sample, mode=mode)
    generated_at = shanghai_now().isoformat()
    strategy_description = _resolve_manifest_strategy_description(strategy.description)
    parameter_snapshot = _resolve_manifest_parameter_snapshot(strategy.parameters)
    equity_curve = [
        {
            "time": point.event_time.isoformat(),
            "value": float(point.equity),
            "baseline": baseline,
        }
        for point in result.equity_curve
    ]

    payload = {
        "datasetName": (f"{dataset.exchange} / {', '.join(dataset.symbols)} / {dataset.timeframe}"),
        "sourceLabel": source_label,
        "sourceMode": source_mode,
        "mode": mode,
        "summary": build_research_summary_payload(
            mode=mode,
            performance=performance,
            sample=sample,
            comparison=comparison,
            experiments=experiments,
        ),
        "klineBars": [
            {
                "time": bar.event_time.isoformat(),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
            }
            for bar in bars
        ],
        "equityCurve": equity_curve,
        "manifest": {
            "runId": str(result.manifest.run_id),
            "accountId": result.manifest.account_id,
            "strategyId": strategy.strategy_id,
            "strategyVersion": _resolve_strategy_version(strategy.strategy_id),
            "handlerName": strategy.handler_name,
            "description": strategy_description,
            "mode": mode,
            "samplePurpose": sample_purpose,
            "symbol": dataset.symbols[0],
            "symbols": list(dataset.symbols),
            "timeframe": dataset.timeframe,
            "barCount": dataset.bar_count,
            "startTime": dataset.start_time.isoformat(),
            "endTime": dataset.end_time.isoformat(),
            "generatedAt": generated_at,
            "initialCash": float(result.manifest.initial_cash),
            "costModel": cost_assumptions.fee_model,
            "slippageBps": float(cost_assumptions.slippage_bps),
            "feeModel": cost_assumptions.fee_model,
            "slippageModel": cost_assumptions.slippage_model,
            "partialFillModel": cost_assumptions.partial_fill_model,
            "unfilledQtyHandling": cost_assumptions.unfilled_qty_handling,
            "executionConstraints": list(cost_assumptions.execution_constraints),
            "parameterSnapshot": parameter_snapshot,
            "dataFingerprint": dataset.data_fingerprint,
            "manifestFingerprint": result.manifest.manifest_fingerprint,
        },
        "performance": {
            **_serialize_performance(performance),
        },
        "decisions": [_serialize_decision(decision) for decision in result.decisions],
        "sample": sample,
        "segments": [_serialize_segment(segment) for segment in segments],
        "experiments": experiments,
        "comparison": comparison,
        "notes": list(notes),
    }
    return payload


def _resolve_manifest_strategy_description(description: str | None) -> str:
    if description is not None and description.strip():
        return description
    return "由事件驱动 research 服务生成的回测结果。"


def _resolve_manifest_parameter_snapshot(
    parameters: dict[str, str],
) -> dict[str, str]:
    return dict(parameters)


def build_research_summary_payload(
    *,
    mode: ResearchMode,
    performance: BacktestPerformanceSummary,
    sample: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
    experiments: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "modeLabel": RESEARCH_MODE_LABELS[mode],
        "resultHeadline": (
            f"净收益 {float(performance.net_pnl):.2f}，"
            f"最大回撤 {float(performance.max_drawdown_pct):.4f}% ，"
            f"交易 {performance.trade_count} 次。"
        ),
        "sampleMessage": _build_sample_message(sample),
        "comparisonMessage": _build_comparison_message(
            mode=mode,
            comparison=comparison,
            experiments=experiments,
        ),
    }


def build_experiments_payload(
    *,
    parameter_sweep: ResearchParameterSweepReport | None = None,
    walk_forward: ResearchWalkForwardReport | None = None,
    baseline_performance: BacktestPerformanceSummary | None = None,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    if parameter_sweep is not None and baseline_performance is not None:
        payload["parameterScan"] = _serialize_parameter_sweep(
            parameter_sweep,
            baseline_performance=baseline_performance,
        )
    if walk_forward is not None:
        payload["walkForward"] = _serialize_walk_forward(walk_forward)
    return payload or None


def build_research_comparison_payload(
    *,
    baseline_result: BacktestRunResult,
    candidate_result: BacktestRunResult,
    baseline_label: str,
    candidate_label: str,
    candidate_kind: Literal["parameter_scan_best_variant", "ai_strategy"],
) -> dict[str, Any]:
    decision_diffs: list[dict[str, Any]] = []
    candidate_decisions = {
        decision.bar_key: decision
        for decision in candidate_result.decisions
    }
    for baseline_decision in baseline_result.decisions:
        candidate_decision = candidate_decisions.get(baseline_decision.bar_key)
        if candidate_decision is None:
            continue
        baseline_action = _resolve_decision_action(baseline_decision)
        candidate_action = _resolve_decision_action(candidate_decision)
        baseline_execution_action = _resolve_execution_action(baseline_decision)
        candidate_execution_action = _resolve_execution_action(candidate_decision)
        if (
            baseline_action == candidate_action
            and baseline_execution_action == candidate_execution_action
            and baseline_decision.order_plan.get("side")
            == candidate_decision.order_plan.get("side")
        ):
            continue
        decision_diffs.append(
            {
                "barKey": baseline_decision.bar_key,
                "eventTime": baseline_decision.event_time.isoformat(),
                "baselineAction": baseline_action,
                "candidateAction": candidate_action,
                "baselineReason": baseline_decision.reason_summary or "",
                "candidateReason": candidate_decision.reason_summary or "",
            }
        )

    return {
        "baselineLabel": baseline_label,
        "candidateLabel": candidate_label,
        "candidateKind": candidate_kind,
        "sameSample": _same_sample(
            baseline_result=baseline_result,
            candidate_result=candidate_result,
        ),
        "sameMetricSemantics": _same_metric_semantics(
            baseline_result=baseline_result,
            candidate_result=candidate_result,
        ),
        "netPnlDelta": float(
            candidate_result.performance.net_pnl - baseline_result.performance.net_pnl
        ),
        "totalReturnDeltaPct": float(
            candidate_result.performance.total_return_pct
            - baseline_result.performance.total_return_pct
        ),
        "maxDrawdownDeltaPct": float(
            candidate_result.performance.max_drawdown_pct
            - baseline_result.performance.max_drawdown_pct
        ),
        "tradeCountDelta": (
            candidate_result.performance.trade_count - baseline_result.performance.trade_count
        ),
        "turnoverDelta": float(
            candidate_result.performance.turnover - baseline_result.performance.turnover
        ),
        "decisionDiffCount": len(decision_diffs),
        "decisionDiffs": decision_diffs,
        "summaryMessage": _build_candidate_summary(
            baseline_label=baseline_label,
            candidate_label=candidate_label,
            candidate_result=candidate_result,
            baseline_result=baseline_result,
        ),
    }


def _resolve_sample_purpose(
    *,
    sample: dict[str, Any] | None,
    mode: ResearchMode,
) -> ResearchSamplePurpose:
    if sample is not None and sample.get("purpose") in {"preview", "evaluation"}:
        return sample["purpose"]
    return resolve_sample_purpose(mode)


def _resolve_strategy_version(strategy_id: str) -> str:
    return strategy_id


def _build_sample_message(sample: dict[str, Any] | None) -> str:
    if sample is None:
        return "等待样本说明。"
    warning = sample.get("warning")
    if isinstance(warning, str) and warning.strip():
        return warning
    description = sample.get("description")
    if isinstance(description, str) and description.strip():
        return description
    return "当前样本说明暂缺。"


def _build_comparison_message(
    *,
    mode: ResearchMode,
    comparison: dict[str, Any] | None,
    experiments: dict[str, Any] | None,
) -> str | None:
    if comparison is not None:
        candidate_label = comparison["candidateLabel"]
        net_pnl_delta = comparison["netPnlDelta"]
        drawdown_delta = comparison["maxDrawdownDeltaPct"]
        trade_count_delta = comparison["tradeCountDelta"]
        return (
            f"{candidate_label} 相比 baseline 的净收益变化 {net_pnl_delta:.2f}，"
            f"最大回撤变化 {drawdown_delta:.4f}% ，交易数变化 {trade_count_delta}。"
        )

    if mode == "walk_forward" and experiments is not None:
        walk_forward = experiments.get("walkForward")
        if isinstance(walk_forward, dict) and walk_forward.get("bestWindowLabel") is not None:
            return (
                f"滚动评估共 {walk_forward['windowCount']} 个窗口，"
                f"当前表现最好的窗口是 {walk_forward['bestWindowLabel']}。"
            )
    return None


def _build_candidate_summary(
    *,
    baseline_label: str,
    candidate_label: str,
    baseline_result: BacktestRunResult,
    candidate_result: BacktestRunResult,
) -> str:
    net_pnl_delta = candidate_result.performance.net_pnl - baseline_result.performance.net_pnl
    drawdown_delta = (
        candidate_result.performance.max_drawdown_pct
        - baseline_result.performance.max_drawdown_pct
    )
    return (
        f"{candidate_label} 基于和 {baseline_label} 相同的样本与成本语义运行；"
        f"净收益变化 {float(net_pnl_delta):.2f}，"
        f"最大回撤变化 {float(drawdown_delta):.4f}% 。"
    )


def _same_sample(
    *,
    baseline_result: BacktestRunResult,
    candidate_result: BacktestRunResult,
) -> bool:
    baseline_dataset = baseline_result.manifest.dataset
    candidate_dataset = candidate_result.manifest.dataset
    return (
        baseline_dataset.symbols == candidate_dataset.symbols
        and baseline_dataset.timeframe == candidate_dataset.timeframe
        and baseline_dataset.bar_count == candidate_dataset.bar_count
        and baseline_dataset.data_fingerprint == candidate_dataset.data_fingerprint
    )


def _same_metric_semantics(
    *,
    baseline_result: BacktestRunResult,
    candidate_result: BacktestRunResult,
) -> bool:
    baseline_cost = baseline_result.manifest.cost_assumptions
    candidate_cost = candidate_result.manifest.cost_assumptions
    return (
        baseline_result.manifest.initial_cash == candidate_result.manifest.initial_cash
        and baseline_cost.fee_model == candidate_cost.fee_model
        and baseline_cost.slippage_model == candidate_cost.slippage_model
        and baseline_cost.partial_fill_model == candidate_cost.partial_fill_model
        and baseline_cost.unfilled_qty_handling == candidate_cost.unfilled_qty_handling
        and baseline_cost.execution_constraints == candidate_cost.execution_constraints
    )


def _serialize_decision(decision: BacktestDecisionRecord) -> dict[str, Any]:
    signal_type: str | None = None
    target_position: float | None = None
    if decision.signal is not None:
        signal_type = decision.signal.signal_type.value
        target_position = float(decision.signal.target_position)
    elif decision.signal_snapshot is not None:
        raw_signal_type = decision.signal_snapshot.get("signal_type")
        signal_type = None if raw_signal_type is None else str(raw_signal_type)

    order_plan_side = decision.order_plan.get("side")
    execution_action = _resolve_execution_action(decision)
    action = _resolve_decision_action(decision)
    return {
        "barKey": decision.bar_key,
        "eventTime": decision.event_time.isoformat(),
        "symbol": decision.symbol,
        "signalType": signal_type,
        "action": action,
        "executionAction": execution_action,
        "targetPosition": target_position,
        "reasonSummary": decision.reason_summary or "",
        "audit": _serialize_audit_summary(decision.audit_summary),
        "skipReason": decision.skip_reason,
        "fillCount": decision.fill_count,
        "orderPlanSide": None if order_plan_side is None else str(order_plan_side),
    }


def _resolve_decision_action(decision: BacktestDecisionRecord) -> str:
    if decision.input_snapshot.get("decision_action"):
        return str(decision.input_snapshot["decision_action"]).strip().upper()
    if decision.signal is not None:
        return decision.signal.signal_type.value.upper()
    if decision.signal_snapshot is not None and decision.signal_snapshot.get("signal_type"):
        return str(decision.signal_snapshot["signal_type"]).strip().upper()
    return "SKIP"


def _resolve_execution_action(decision: BacktestDecisionRecord) -> str:
    order_plan_side = decision.order_plan.get("side")
    return order_plan_side if order_plan_side in {"BUY", "SELL"} else "SKIP"


def _serialize_performance(performance: BacktestPerformanceSummary) -> dict[str, Any]:
    return {
        "barCount": performance.bar_count,
        "signalCount": performance.signal_count,
        "orderCount": performance.order_count,
        "tradeCount": performance.trade_count,
        "fillCount": performance.fill_count,
        "winningTradeCount": performance.winning_trade_count,
        "losingTradeCount": performance.losing_trade_count,
        "startingCash": float(performance.starting_cash),
        "endingCash": float(performance.ending_cash),
        "endingMarketValue": float(performance.ending_market_value),
        "startingEquity": float(performance.starting_equity),
        "endingEquity": float(performance.ending_equity),
        "netPnl": float(performance.net_pnl),
        "totalReturnPct": float(performance.total_return_pct),
        "maxDrawdownPct": float(performance.max_drawdown_pct),
        "realizedPnl": float(performance.realized_pnl),
        "unrealizedPnl": float(performance.unrealized_pnl),
        "turnover": float(performance.turnover),
        "winRatePct": (
            None if performance.win_rate_pct is None else float(performance.win_rate_pct)
        ),
        "sharpeRatio": (
            None if performance.sharpe_ratio is None else float(performance.sharpe_ratio)
        ),
        "returnToDrawdownRatio": (
            None
            if performance.return_to_drawdown_ratio is None
            else float(performance.return_to_drawdown_ratio)
        ),
        "profitFactor": (
            None if performance.profit_factor is None else float(performance.profit_factor)
        ),
        "avgTradePnl": (
            None if performance.avg_trade_pnl is None else float(performance.avg_trade_pnl)
        ),
        "avgWinningTradePnl": (
            None
            if performance.avg_winning_trade_pnl is None
            else float(performance.avg_winning_trade_pnl)
        ),
        "avgLosingTradePnl": (
            None
            if performance.avg_losing_trade_pnl is None
            else float(performance.avg_losing_trade_pnl)
        ),
        "avgHoldingBars": (
            None if performance.avg_holding_bars is None else float(performance.avg_holding_bars)
        ),
    }


def _serialize_audit_summary(
    audit_summary: dict[str, str | bool | None] | None,
) -> dict[str, str | bool | None] | None:
    if audit_summary is None:
        return None
    return {
        "providerId": audit_summary.get("provider_id"),
        "modelOrPolicyVersion": audit_summary.get("model_or_policy_version"),
        "decision": audit_summary.get("decision"),
        "confidence": audit_summary.get("confidence"),
        "reasonSummary": audit_summary.get("reason_summary"),
        "fallbackUsed": audit_summary.get("fallback_used"),
        "fallbackReason": audit_summary.get("fallback_reason"),
    }


def _serialize_segment(segment: ResearchSegmentAnalysis) -> dict[str, Any]:
    return {
        "label": segment.label,
        "marketRegime": segment.market_regime,
        "marketRegimeLabel": segment.market_regime_label,
        "startTime": segment.start_time.isoformat(),
        "endTime": segment.end_time.isoformat(),
        "barCount": segment.bar_count,
        "priceChangePct": float(segment.price_change_pct),
        "performance": _serialize_performance(segment.performance),
    }


def _serialize_parameter_sweep(
    report: ResearchParameterSweepReport,
    *,
    baseline_performance: BacktestPerformanceSummary,
) -> dict[str, Any]:
    variants = []
    best_variant = None
    for variant in report.variants:
        payload = {
            "label": variant.label,
            "strategyId": variant.strategy_id,
            "handlerName": variant.handler_name,
            "parameters": dict(variant.parameters),
            "performance": _serialize_performance(variant.performance),
            "manifestFingerprint": variant.manifest_fingerprint,
            "versusBaseline": _serialize_delta(
                candidate_performance=variant.performance,
                baseline_performance=baseline_performance,
            ),
        }
        if variant.label == report.best_variant_label:
            best_variant = payload
        variants.append(payload)

    return {
        "strategyId": report.strategy_id,
        "combinationCount": report.combination_count,
        "rankingMetric": report.ranking_metric,
        "bestVariantLabel": report.best_variant_label,
        "bestVariant": best_variant,
        "variants": variants,
    }


def _serialize_walk_forward(report: ResearchWalkForwardReport) -> dict[str, Any]:
    windows = []
    best_window = None
    positive_window_count = 0
    for window in report.windows:
        payload = {
            "label": window.label,
            "startTime": window.start_time.isoformat(),
            "endTime": window.end_time.isoformat(),
            "barCount": window.bar_count,
            "performance": _serialize_performance(window.performance),
            "manifestFingerprint": window.manifest_fingerprint,
        }
        if window.performance.net_pnl > Decimal("0"):
            positive_window_count += 1
        if window.label == report.best_window_label:
            best_window = payload
        windows.append(payload)

    return {
        "method": report.method,
        "strategyId": report.strategy_id,
        "windowBars": report.window_bars,
        "stepBars": report.step_bars,
        "windowCount": report.window_count,
        "bestWindowLabel": report.best_window_label,
        "bestWindow": best_window,
        "positiveWindowCount": positive_window_count,
        "windows": windows,
    }


def _serialize_delta(
    *,
    candidate_performance: BacktestPerformanceSummary,
    baseline_performance: BacktestPerformanceSummary,
) -> dict[str, Any]:
    return {
        "netPnlDelta": float(candidate_performance.net_pnl - baseline_performance.net_pnl),
        "totalReturnDeltaPct": float(
            candidate_performance.total_return_pct - baseline_performance.total_return_pct
        ),
        "maxDrawdownDeltaPct": float(
            candidate_performance.max_drawdown_pct - baseline_performance.max_drawdown_pct
        ),
        "tradeCountDelta": candidate_performance.trade_count - baseline_performance.trade_count,
        "turnoverDelta": float(candidate_performance.turnover - baseline_performance.turnover),
    }
