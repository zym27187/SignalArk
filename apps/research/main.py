"""Research CLI for running minimal event-driven backtests from JSON bars."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.config import load_settings
from src.domain.events import BarEvent
from src.services.backtest import BacktestDecisionRecord, BacktestRunResult

from apps.research import build_default_backtest_runner

BAR_EVENT_FIELD_NAMES = frozenset(BarEvent.model_fields)


def main() -> None:
    """Run the research CLI and export the resulting backtest payload."""
    args = _build_parser().parse_args()
    asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> None:
    settings = _load_cli_settings(args)
    bars = _load_bar_events(Path(args.input))
    runner = build_default_backtest_runner(
        settings,
        initial_cash=args.initial_cash,
        slippage_bps=args.slippage_bps,
    )
    result = await runner.run(bars)

    result_payload = result.model_dump(mode="json")
    if args.output is not None:
        output_path = Path(args.output)
        _write_json(output_path, result_payload)
        print(f"Backtest result written to {output_path}")
    else:
        print(json.dumps(result_payload, ensure_ascii=False, indent=2))

    if args.web_snapshot_output is not None:
        snapshot_path = Path(args.web_snapshot_output)
        snapshot_payload = _build_web_snapshot(
            result=result,
            bars=bars,
        )
        _write_json(snapshot_path, snapshot_payload)
        print(f"Web snapshot written to {snapshot_path}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        help=(
            "Path to a JSON file containing a list of BarEvent payloads or "
            "an object with a bars field."
        ),
    )
    parser.add_argument(
        "--output",
        help="Optional path for the BacktestRunResult JSON. Defaults to stdout.",
    )
    parser.add_argument(
        "--web-snapshot-output",
        help=(
            "Optional path for a frontend-friendly research snapshot JSON aligned with "
            "apps/web/src/lib/research-fixtures.ts."
        ),
    )
    parser.add_argument(
        "--initial-cash",
        type=Decimal,
        default=Decimal("100000"),
        help="Initial cash used for the backtest. Defaults to 100000.",
    )
    parser.add_argument(
        "--slippage-bps",
        type=Decimal,
        default=Decimal("5"),
        help="Slippage in basis points applied by the paper execution model. Defaults to 5.",
    )
    parser.add_argument(
        "--config-profile",
        help=(
            "Optional settings profile to load before env overrides. "
            "Defaults to the repo default profile."
        ),
    )
    parser.add_argument(
        "--config-file",
        help="Optional extra config file layered on top of the selected profile.",
    )
    parser.add_argument(
        "--postgres-dsn",
        help=(
            "Optional DSN override used only to satisfy shared settings validation. "
            "Defaults to sqlite+pysqlite:///:memory: when omitted."
        ),
    )
    return parser


def _load_cli_settings(args: argparse.Namespace):
    postgres_dsn = args.postgres_dsn or os.environ.get(
        "SIGNALARK_POSTGRES_DSN",
        "sqlite+pysqlite:///:memory:",
    )
    os.environ.setdefault("SIGNALARK_POSTGRES_DSN", postgres_dsn)
    return load_settings(
        config_profile=args.config_profile,
        config_file=args.config_file,
    )


def _load_bar_events(path: Path) -> list[BarEvent]:
    raw_payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw_payload, list):
        items = raw_payload
    elif isinstance(raw_payload, dict):
        candidate = raw_payload.get("bars", raw_payload.get("events"))
        if not isinstance(candidate, list):
            raise ValueError("Input JSON object must contain a list field named bars or events.")
        items = candidate
    else:
        raise ValueError(
            "Input JSON must be a list of BarEvent payloads "
            "or an object containing one."
        )

    bars: list[BarEvent] = []
    for item in items:
        if not isinstance(item, dict):
            raise TypeError("Every input bar must be a JSON object compatible with BarEvent.")
        normalized_item = {
            key: value
            for key, value in item.items()
            if key in BAR_EVENT_FIELD_NAMES
        }
        bars.append(BarEvent(**normalized_item))
    return bars


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_web_snapshot(
    *,
    result: BacktestRunResult,
    bars: list[BarEvent],
) -> dict[str, Any]:
    dataset = result.manifest.dataset
    strategy = result.manifest.strategy
    cost_assumptions = result.manifest.cost_assumptions
    performance = result.performance
    baseline = float(performance.starting_equity)
    backtest_equity_curve = [
        {
            "time": point.event_time.isoformat(),
            "value": float(point.equity),
            "baseline": baseline,
        }
        for point in result.equity_curve
    ]

    return {
        "datasetName": (
            f"{dataset.exchange} / {', '.join(dataset.symbols)} / {dataset.timeframe}"
        ),
        "sourceLabel": "由 research CLI 导出的真实回测结果",
        "sourceMode": "fixture",
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
        "runtimePnlCurve": backtest_equity_curve,
        "backtestEquityCurve": backtest_equity_curve,
        "manifest": {
            "runId": str(result.manifest.run_id),
            "accountId": result.manifest.account_id,
            "strategyId": strategy.strategy_id,
            "handlerName": strategy.handler_name,
            "description": strategy.description or "由 research CLI 导出的事件驱动回测结果。",
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
        },
        "decisions": [_serialize_decision(decision) for decision in result.decisions],
        "notes": [
            "该文件由 `python -m apps.research` 生成，可作为真实回测导出结果留档。",
            "如需前端直接展示真实研究结果，后续可在 HTTP 接口中复用这份导出契约。",
            "当前 runtimePnlCurve 使用与 backtestEquityCurve 相同的导出曲线作为占位。",
        ],
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
    action = order_plan_side if order_plan_side in {"BUY", "SELL"} else "SKIP"
    return {
        "barKey": decision.bar_key,
        "eventTime": decision.event_time.isoformat(),
        "symbol": decision.symbol,
        "signalType": signal_type,
        "action": action,
        "targetPosition": target_position,
        "reasonSummary": decision.reason_summary or "",
        "skipReason": decision.skip_reason,
        "fillCount": decision.fill_count,
        "orderPlanSide": None if order_plan_side is None else str(order_plan_side),
    }


if __name__ == "__main__":
    main()
