"""Shared serializers for frontend-facing research snapshot payloads."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from apps.research.analysis import ResearchSegmentAnalysis
from src.domain.events import BarEvent
from src.services.backtest import BacktestDecisionRecord, BacktestRunResult

ResearchSnapshotSourceMode = Literal["fixture", "imported", "live"]


def build_web_snapshot_payload(
    *,
    result: BacktestRunResult,
    bars: Sequence[BarEvent],
    source_label: str,
    source_mode: ResearchSnapshotSourceMode,
    notes: Sequence[str],
    sample: dict[str, Any] | None = None,
    segments: Sequence[ResearchSegmentAnalysis] = (),
) -> dict[str, Any]:
    """Serialize a backtest result into the research page snapshot contract."""
    dataset = result.manifest.dataset
    strategy = result.manifest.strategy
    cost_assumptions = result.manifest.cost_assumptions
    performance = result.performance
    baseline = float(performance.starting_equity)
    equity_curve = [
        {
            "time": point.event_time.isoformat(),
            "value": float(point.equity),
            "baseline": baseline,
        }
        for point in result.equity_curve
    ]

    return {
        "datasetName": (f"{dataset.exchange} / {', '.join(dataset.symbols)} / {dataset.timeframe}"),
        "sourceLabel": source_label,
        "sourceMode": source_mode,
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
            "handlerName": strategy.handler_name,
            "description": strategy.description or "由事件驱动 research 服务生成的回测结果。",
            "symbols": list(dataset.symbols),
            "timeframe": dataset.timeframe,
            "barCount": dataset.bar_count,
            "startTime": dataset.start_time.isoformat(),
            "endTime": dataset.end_time.isoformat(),
            "initialCash": float(result.manifest.initial_cash),
            "slippageBps": float(cost_assumptions.slippage_bps),
            "feeModel": cost_assumptions.fee_model,
            "slippageModel": cost_assumptions.slippage_model,
            "dataFingerprint": dataset.data_fingerprint,
            "manifestFingerprint": result.manifest.manifest_fingerprint,
        },
        "performance": {
            **_serialize_performance(performance),
        },
        "decisions": [_serialize_decision(decision) for decision in result.decisions],
        "sample": sample,
        "segments": [_serialize_segment(segment) for segment in segments],
        "notes": list(notes),
    }


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
    execution_action = order_plan_side if order_plan_side in {"BUY", "SELL"} else "SKIP"
    raw_decision_action = decision.input_snapshot.get("decision_action")
    if isinstance(raw_decision_action, str) and raw_decision_action.strip():
        action = raw_decision_action.strip().upper()
    elif signal_type is not None and signal_type.strip():
        action = signal_type.strip().upper()
    else:
        action = "SKIP"
    return {
        "barKey": decision.bar_key,
        "eventTime": decision.event_time.isoformat(),
        "symbol": decision.symbol,
        "signalType": signal_type,
        "action": action,
        "executionAction": execution_action,
        "targetPosition": target_position,
        "reasonSummary": decision.reason_summary or "",
        "skipReason": decision.skip_reason,
        "fillCount": decision.fill_count,
        "orderPlanSide": None if order_plan_side is None else str(order_plan_side),
    }


def _serialize_performance(performance) -> dict[str, Any]:
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
        "winRatePct": None if performance.win_rate_pct is None else float(performance.win_rate_pct),
        "sharpeRatio": None if performance.sharpe_ratio is None else float(performance.sharpe_ratio),
        "returnToDrawdownRatio": (
            None
            if performance.return_to_drawdown_ratio is None
            else float(performance.return_to_drawdown_ratio)
        ),
        "profitFactor": (
            None if performance.profit_factor is None else float(performance.profit_factor)
        ),
        "avgTradePnl": None if performance.avg_trade_pnl is None else float(performance.avg_trade_pnl),
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
