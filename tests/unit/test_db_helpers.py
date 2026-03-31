from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from src.domain.strategy import Signal, SignalType
from src.infra.db import EventLogEntry, normalize_database_url

BASE_TIME = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
TRADER_RUN_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def test_normalize_database_url_upgrades_plain_postgresql_scheme() -> None:
    normalized = normalize_database_url("postgresql://signalark:signalark@localhost:5432/signalark")

    assert normalized == "postgresql+psycopg://signalark:signalark@localhost:5432/signalark"


def test_event_log_entry_normalizes_domain_payloads_into_json_safe_values() -> None:
    signal = Signal(
        strategy_id="baseline_momentum_v1",
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="BINANCE",
        symbol="btcusdt",
        timeframe="15M",
        signal_type=SignalType.ENTRY,
        target_position=Decimal("0.5"),
        confidence=Decimal("0.85"),
        event_time=BASE_TIME,
        created_at=BASE_TIME + timedelta(seconds=1),
    )
    event = EventLogEntry(
        event_type="signal.persisted",
        source="trader",
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="binance",
        symbol="BTCUSDT",
        event_time=BASE_TIME + timedelta(seconds=1),
        ingest_time=BASE_TIME + timedelta(seconds=2),
        created_at=BASE_TIME + timedelta(seconds=3),
        payload_json={
            "signal": signal,
            "decision_price": Decimal("101.25"),
            "related_ids": [TRADER_RUN_ID],
        },
    )

    assert event.exchange == "binance"
    assert event.symbol == "BTCUSDT"
    assert event.payload_json["signal"]["exchange"] == "binance"
    assert event.payload_json["signal"]["symbol"] == "BTCUSDT"
    assert event.payload_json["decision_price"] == "101.25"
    assert event.payload_json["related_ids"] == [str(TRADER_RUN_ID)]
