from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.domain.market import FinalBarGate
from src.infra.exchanges import EastmoneyAshareBarNormalizer

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_END_LOCAL = datetime(2026, 3, 31, 14, 30, tzinfo=SHANGHAI)
TIMEFRAME = "15m"


def _kline_row(
    bar_end_local: datetime,
    *,
    open_price: str = "39.47",
    close_price: str = "39.42",
    high_price: str = "39.49",
    low_price: str = "39.41",
    volume_lots: str = "26744",
    amount_cny: str = "105520962.00",
    amplitude_pct: str = "0.20",
    pct_change: str = "-0.13",
    change_amount: str = "-0.05",
    turnover_pct: str = "0.31",
) -> str:
    return ",".join(
        [
            bar_end_local.strftime("%Y-%m-%d %H:%M"),
            open_price,
            close_price,
            high_price,
            low_price,
            volume_lots,
            amount_cny,
            amplitude_pct,
            pct_change,
            change_amount,
            turnover_pct,
        ]
    )


def test_eastmoney_kline_normalizes_symbol_timezone_precision_and_source_payload() -> None:
    normalizer = EastmoneyAshareBarNormalizer(clock=lambda: BASE_END_LOCAL + timedelta(minutes=5))

    bar = normalizer.from_kline_row(
        _kline_row(BASE_END_LOCAL),
        symbol="600036.sh",
        timeframe=TIMEFRAME,
        source_kind="historical",
    )
    event = bar.to_bar_event()

    assert event.exchange == "cn_equity"
    assert event.symbol == "600036.SH"
    assert event.timeframe == "15m"
    assert event.bar_start_time == BASE_END_LOCAL - timedelta(minutes=15)
    assert event.bar_end_time == BASE_END_LOCAL
    assert event.close == Decimal("39.42")
    assert event.volume == Decimal("2674400")
    assert event.quote_volume == Decimal("105520962.00")
    assert event.closed is True
    assert event.final is True
    assert event.actionable is True
    assert event.bar_key == "cn_equity:600036.SH:15m:2026-03-31T14:15:00+08:00"
    assert event.source_kind == "historical"
    assert event.source_payload["source"] == "eastmoney_kline"
    assert event.source_payload["volume_lots"] == "26744"
    assert event.market_state is not None
    assert event.market_state.trade_date.isoformat() == "2026-03-31"
    assert event.market_state.previous_close == Decimal("39.47")
    assert event.market_state.upper_limit_price == Decimal("43.42")
    assert event.market_state.lower_limit_price == Decimal("35.52")


def test_eastmoney_open_bar_stays_non_actionable_until_bar_end() -> None:
    normalizer = EastmoneyAshareBarNormalizer(clock=lambda: BASE_END_LOCAL - timedelta(minutes=5))
    gate = FinalBarGate()

    decision = gate.process(
        normalizer.from_kline_row(
            _kline_row(BASE_END_LOCAL),
            symbol="600036.SH",
            timeframe=TIMEFRAME,
            source_kind="realtime",
        )
    )

    assert decision.status == "non_actionable"
    assert decision.event.source_kind == "realtime"
    assert decision.event.closed is False
    assert decision.event.final is False
    assert decision.event.actionable is False
    assert decision.event.market_state is not None


def test_final_bar_gate_deduplicates_history_and_realtime_with_same_bar_key() -> None:
    gate = FinalBarGate()
    history_normalizer = EastmoneyAshareBarNormalizer(
        clock=lambda: BASE_END_LOCAL + timedelta(minutes=5)
    )
    realtime_normalizer = EastmoneyAshareBarNormalizer(
        clock=lambda: BASE_END_LOCAL + timedelta(minutes=1)
    )

    first = gate.process(
        history_normalizer.from_kline_row(
            _kline_row(BASE_END_LOCAL),
            symbol="600036.SH",
            timeframe=TIMEFRAME,
            source_kind="historical",
        )
    )
    second = gate.process(
        realtime_normalizer.from_kline_row(
            _kline_row(BASE_END_LOCAL),
            symbol="600036.SH",
            timeframe=TIMEFRAME,
            source_kind="realtime",
        )
    )

    assert first.status == "emit"
    assert second.status == "duplicate"
    assert second.event.bar_key == first.event.bar_key
    assert gate.next_expected_bar_start("cn_equity", "600036.SH", TIMEFRAME) == BASE_END_LOCAL
