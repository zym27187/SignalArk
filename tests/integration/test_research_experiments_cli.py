from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from src.domain.events import BarEvent
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase

ROOT_DIR = Path(__file__).resolve().parents[2]
SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 1, 10, 0, tzinfo=SHANGHAI)


def _market_state(*, trade_date: date, previous_close: Decimal) -> MarketStateSnapshot:
    upper_limit = (previous_close * Decimal("1.10")).quantize(Decimal("0.01"))
    lower_limit = (previous_close * Decimal("0.90")).quantize(Decimal("0.01"))
    return MarketStateSnapshot(
        trade_date=trade_date,
        previous_close=previous_close,
        upper_limit_price=upper_limit,
        lower_limit_price=lower_limit,
        trading_phase=TradingPhase.CONTINUOUS_AUCTION,
        suspension_status=SuspensionStatus.ACTIVE,
    )


def _bar_event(
    *,
    index: int,
    close: Decimal,
    previous_close: Decimal,
) -> BarEvent:
    event_time = BASE_TIME + timedelta(minutes=15 * index)
    return BarEvent(
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        bar_start_time=event_time - timedelta(minutes=15),
        bar_end_time=event_time,
        event_time=event_time,
        ingest_time=event_time + timedelta(seconds=2),
        open=previous_close,
        high=max(close, previous_close),
        low=min(close, previous_close),
        close=close,
        volume=Decimal("1000"),
        closed=True,
        final=True,
        source_kind="historical",
        market_state=_market_state(
            trade_date=event_time.date(),
            previous_close=previous_close,
        ),
    )


def test_research_cli_exports_parameter_sweep_and_walk_forward_report(tmp_path: Path) -> None:
    input_path = tmp_path / "bars.json"
    experiment_output_path = tmp_path / "research-experiments.json"
    sweep_grid_path = tmp_path / "baseline-grid.json"

    closes = [
        Decimal("39.48"),
        Decimal("39.49"),
        Decimal("39.52"),
        Decimal("39.56"),
        Decimal("39.61"),
        Decimal("39.67"),
        Decimal("39.63"),
        Decimal("39.58"),
        Decimal("39.55"),
        Decimal("39.60"),
        Decimal("39.66"),
        Decimal("39.72"),
    ]
    bars = []
    previous_close = Decimal("39.47")
    for index, close in enumerate(closes):
        bars.append(
            _bar_event(
                index=index,
                close=close,
                previous_close=previous_close,
            )
        )
        previous_close = close

    input_path.write_text(
        json.dumps({"bars": [bar.model_dump(mode="json") for bar in bars]}, ensure_ascii=False),
        encoding="utf-8",
    )
    sweep_grid_path.write_text(
        json.dumps(
            {
                "entry_threshold_pct": ["0.0005", "0.0010"],
                "trend_lookback_bars": [3, 4],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    env = dict(os.environ)
    env.pop("SIGNALARK_POSTGRES_DSN", None)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "apps.research",
            "--input",
            str(input_path),
            "--experiment-output",
            str(experiment_output_path),
            "--baseline-sweep-grid",
            str(sweep_grid_path),
            "--walk-forward-window-bars",
            "6",
            "--walk-forward-step-bars",
            "3",
        ],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(experiment_output_path.read_text(encoding="utf-8"))

    assert "Experiment report written" in completed.stdout
    assert payload["parameter_sweep"]["combination_count"] == 4
    assert len(payload["parameter_sweep"]["variants"]) == 4
    assert payload["parameter_sweep"]["best_variant_label"] is not None
    assert payload["parameter_sweep"]["ranking_metric"] == "sharpe_ratio_then_net_pnl"
    assert payload["walk_forward"]["window_bars"] == 6
    assert payload["walk_forward"]["step_bars"] == 3
    assert payload["walk_forward"]["window_count"] == 3
    assert len(payload["walk_forward"]["windows"]) == 3
    assert payload["walk_forward"]["best_window_label"] is not None
