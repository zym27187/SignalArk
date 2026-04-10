"""Research CLI for running minimal event-driven backtests from JSON bars."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path

from src.config import load_settings
from src.domain.events import BarEvent

from apps.research import build_default_backtest_runner
from apps.research.analysis import build_sample_metadata, build_segment_analyses
from apps.research.experiments import (
    ResearchExperimentReport,
    load_baseline_sweep_grid,
    run_baseline_parameter_sweep,
    run_walk_forward_evaluation,
)
from apps.research.snapshot import build_web_snapshot_payload

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
        slippage_model=args.slippage_model,
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
        sample_metadata = build_sample_metadata(
            sample_purpose=args.sample_purpose,
            requested_bar_count=len(bars),
            actual_bar_count=len(bars),
        )

        async def run_segment_backtest(segment_bars: list[BarEvent]) -> object:
            return await build_default_backtest_runner(
                settings,
                initial_cash=args.initial_cash,
                slippage_bps=args.slippage_bps,
                slippage_model=args.slippage_model,
            ).run(segment_bars)

        segment_analyses = await build_segment_analyses(
            bars=bars,
            run_backtest=run_segment_backtest,
            sample_purpose=args.sample_purpose,
        )
        snapshot_notes = [
            "该文件由 `python -m apps.research` 生成，可作为真实回测导出结果留档。",
            "该导出来源会显式标记为 imported，而不是继续混用 fixture 语义。",
            "该导出会统一使用 `equityCurve` 表示 research 回测权益曲线。",
            "前端与 HTTP research snapshot 会复用同一份研究快照契约。",
            (
                "当前 backtest 仍保持整笔成交，不模拟部分成交和成交失败；"
                "剩余执行差异会写入 manifest.executionConstraints。"
            ),
        ]
        if sample_metadata["warning"] is not None:
            snapshot_notes.append(str(sample_metadata["warning"]))
        if segment_analyses:
            snapshot_notes.append(
                f"时间分段评估会把样本按时间切成 {len(segment_analyses)} 段，"
                "并在同一起始资金下分别比较阶段表现。"
            )
        snapshot_payload = build_web_snapshot_payload(
            result=result,
            bars=bars,
            source_label="由 research CLI 导出的真实回测结果",
            source_mode="imported",
            notes=tuple(snapshot_notes),
            sample=sample_metadata,
            segments=segment_analyses,
        )
        _write_json(snapshot_path, snapshot_payload)
        print(f"Web snapshot written to {snapshot_path}")

    if args.experiment_output is not None:
        if args.baseline_sweep_grid is None and args.walk_forward_window_bars is None:
            raise ValueError(
                "experiment output requires --baseline-sweep-grid and/or "
                "--walk-forward-window-bars"
            )

        parameter_sweep = None
        if args.baseline_sweep_grid is not None:
            parameter_sweep = await run_baseline_parameter_sweep(
                settings=settings,
                bars=bars,
                parameter_grid=load_baseline_sweep_grid(Path(args.baseline_sweep_grid)),
                initial_cash=args.initial_cash,
                slippage_bps=args.slippage_bps,
                slippage_model=args.slippage_model,
            )

        walk_forward = None
        if args.walk_forward_window_bars is not None:
            walk_forward = await run_walk_forward_evaluation(
                settings=settings,
                bars=bars,
                window_bars=args.walk_forward_window_bars,
                step_bars=args.walk_forward_step_bars,
                initial_cash=args.initial_cash,
                slippage_bps=args.slippage_bps,
                slippage_model=args.slippage_model,
            )

        experiment_output_path = Path(args.experiment_output)
        experiment_payload = ResearchExperimentReport(
            dataset_bar_count=len(bars),
            parameter_sweep=parameter_sweep,
            walk_forward=walk_forward,
        ).model_dump(mode="json")
        _write_json(experiment_output_path, experiment_payload)
        print(f"Experiment report written to {experiment_output_path}")


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
        "--experiment-output",
        help="Optional path for a parameter sweep / walk-forward experiment report JSON.",
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
        "--slippage-model",
        choices=("bar_close_bps", "directional_close_tiered_bps"),
        default="bar_close_bps",
        help=(
            "Slippage model used by the backtest runner. "
            "Defaults to fixed bar_close_bps."
        ),
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
    parser.add_argument(
        "--sample-purpose",
        choices=("preview", "evaluation"),
        default="evaluation",
        help=(
            "How the frontend-oriented web snapshot should label this sample. "
            "Defaults to evaluation."
        ),
    )
    parser.add_argument(
        "--baseline-sweep-grid",
        help=(
            "Optional JSON/YAML file describing baseline parameter lists to sweep. "
            "Used together with --experiment-output."
        ),
    )
    parser.add_argument(
        "--walk-forward-window-bars",
        type=int,
        help=(
            "Optional rolling-evaluation window size in bars. "
            "Used together with --experiment-output."
        ),
    )
    parser.add_argument(
        "--walk-forward-step-bars",
        type=int,
        help=(
            "Optional rolling-evaluation step size in bars. "
            "Defaults to the same value as --walk-forward-window-bars."
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
            "Input JSON must be a list of BarEvent payloads or an object containing one."
        )

    bars: list[BarEvent] = []
    for item in items:
        if not isinstance(item, dict):
            raise TypeError("Every input bar must be a JSON object compatible with BarEvent.")
        normalized_item = {
            key: value for key, value in item.items() if key in BAR_EVENT_FIELD_NAMES
        }
        bars.append(BarEvent(**normalized_item))
    return bars


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
