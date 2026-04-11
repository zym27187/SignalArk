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
DAY_ONE = datetime(2026, 4, 1, 14, 0, tzinfo=SHANGHAI)
DAY_TWO = datetime(2026, 4, 2, 14, 0, tzinfo=SHANGHAI)


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
    event_time: datetime,
    close: Decimal,
    previous_close: Decimal,
) -> BarEvent:
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


def test_research_cli_runs_backtest_and_exports_result_files(tmp_path: Path) -> None:
    input_path = tmp_path / "bars.json"
    output_path = tmp_path / "backtest-result.json"
    snapshot_path = tmp_path / "research-snapshot.json"

    bars = [
        _bar_event(
            event_time=DAY_ONE,
            close=Decimal("39.48"),
            previous_close=Decimal("39.47"),
        ),
        _bar_event(
            event_time=DAY_ONE + timedelta(minutes=15),
            close=Decimal("39.49"),
            previous_close=Decimal("39.47"),
        ),
        _bar_event(
            event_time=DAY_ONE + timedelta(minutes=30),
            close=Decimal("39.50"),
            previous_close=Decimal("39.47"),
        ),
        _bar_event(
            event_time=DAY_ONE + timedelta(minutes=45),
            close=Decimal("39.52"),
            previous_close=Decimal("39.47"),
        ),
        _bar_event(
            event_time=DAY_TWO,
            close=Decimal("39.10"),
            previous_close=Decimal("39.52"),
        ),
    ]
    input_path.write_text(
        json.dumps({"bars": [bar.model_dump(mode="json") for bar in bars]}, ensure_ascii=False),
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
            "--output",
            str(output_path),
            "--web-snapshot-output",
            str(snapshot_path),
            "--sample-purpose",
            "evaluation",
            "--initial-cash",
            "100000",
            "--slippage-bps",
            "5",
            "--slippage-model",
            "directional_close_tiered_bps",
        ],
        cwd=ROOT_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    result_payload = json.loads(output_path.read_text(encoding="utf-8"))
    snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert "Backtest result written" in completed.stdout
    assert "Web snapshot written" in completed.stdout

    assert result_payload["performance"]["trade_count"] == 3
    assert result_payload["performance"]["fill_count"] == 3
    assert result_payload["manifest"]["cost_assumptions"]["slippage_model"] == (
        "directional_close_tiered_bps"
    )
    assert len(result_payload["decisions"]) == 5
    assert len(result_payload["equity_curve"]) == 5
    assert result_payload["decisions"][0]["skip_reason"] == "baseline_trend_warmup"
    assert Decimal(result_payload["decisions"][2]["signal"]["target_position"]) == Decimal("200")
    assert result_payload["decisions"][4]["order_plan"]["side"] == "SELL"

    assert snapshot_payload["sourceLabel"] == "由 research CLI 导出的真实回测结果"
    assert snapshot_payload["sourceMode"] == "imported"
    assert snapshot_payload["mode"] == "evaluation"
    assert snapshot_payload["summary"]["modeLabel"] == "评估样本"
    assert snapshot_payload["manifest"]["strategyId"] == "baseline_momentum_v1"
    assert snapshot_payload["manifest"]["strategyVersion"] == "baseline_momentum_v1"
    assert snapshot_payload["manifest"]["mode"] == "evaluation"
    assert snapshot_payload["manifest"]["samplePurpose"] == "evaluation"
    assert snapshot_payload["manifest"]["symbol"] == "600036.SH"
    assert snapshot_payload["manifest"]["slippageModel"] == "directional_close_tiered_bps"
    assert snapshot_payload["manifest"]["partialFillModel"] == "full_fill_only"
    assert snapshot_payload["manifest"]["parameterSnapshot"]["target_position"] == "400"
    assert "partial fills" in " ".join(snapshot_payload["manifest"]["executionConstraints"])
    assert snapshot_payload["performance"]["tradeCount"] == 3
    assert snapshot_payload["performance"]["sharpeRatio"] is not None
    assert snapshot_payload["performance"]["avgHoldingBars"] == 1.5
    assert snapshot_payload["sample"]["purpose"] == "evaluation"
    assert snapshot_payload["sample"]["actualBarCount"] == 5
    assert snapshot_payload["segments"] == []
    assert snapshot_payload["experiments"] is None
    assert snapshot_payload["comparison"] is None
    assert len(snapshot_payload["klineBars"]) == 5
    assert len(snapshot_payload["equityCurve"]) == 5
    assert "runtimePnlCurve" not in snapshot_payload
    assert "backtestEquityCurve" not in snapshot_payload
    assert snapshot_payload["decisions"][0]["executionAction"] == "SKIP"
    assert snapshot_payload["decisions"][0]["skipReason"] == "baseline_trend_warmup"
    assert snapshot_payload["decisions"][2]["action"] == "REBALANCE"
    assert snapshot_payload["decisions"][2]["orderPlanSide"] == "BUY"
    assert snapshot_payload["decisions"][3]["orderPlanSide"] == "BUY"
    assert snapshot_payload["decisions"][4]["orderPlanSide"] == "SELL"
    assert snapshot_payload["decisions"][4]["action"] == "EXIT"
    assert snapshot_payload["decisions"][4]["executionAction"] == "SELL"
