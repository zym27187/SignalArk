from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.infra.observability import (
    AlertRouter,
    ObservabilityEvent,
    RecordingAlertSink,
    SignalArkObservability,
    TelegramAlertSink,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 1, 16, 0, tzinfo=SHANGHAI)


@dataclass
class MutableClock:
    value: datetime

    def now(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], float]] = []

    def post(
        self,
        url: str,
        *,
        json: dict[str, object],
        timeout: float,
    ) -> None:
        self.calls.append((url, json, timeout))


def test_alert_router_suppresses_duplicate_events_within_cooldown() -> None:
    clock = MutableClock(BASE_TIME)
    sink = RecordingAlertSink()
    observability = SignalArkObservability(
        service="tests",
        alert_router=AlertRouter((sink,), clock=clock.now),
        clock=clock.now,
    )

    payload = observability.emit(
        event_name="control.kill_switch_enabled",
        severity="warning",
        message="Kill switch enabled.",
        notify=True,
        account_id="paper_account_001",
        reason_code="OPERATOR_REQUEST",
    )
    observability.emit(
        event_name="control.kill_switch_enabled",
        severity="warning",
        message="Kill switch enabled.",
        notify=True,
        account_id="paper_account_001",
        reason_code="OPERATOR_REQUEST",
    )

    assert payload["event_name"] == "control.kill_switch_enabled"
    assert payload["severity"] == "warning"
    assert payload["account_id"] == "paper_account_001"
    assert payload["reason_code"] == "OPERATOR_REQUEST"
    assert len(sink.events) == 1

    clock.advance(timedelta(minutes=6))
    observability.emit(
        event_name="control.kill_switch_enabled",
        severity="warning",
        message="Kill switch enabled.",
        notify=True,
        account_id="paper_account_001",
        reason_code="OPERATOR_REQUEST",
    )

    assert len(sink.events) == 2


def test_bypass_cooldown_keeps_immediate_alerts_unsuppressed() -> None:
    clock = MutableClock(BASE_TIME)
    sink = RecordingAlertSink()
    observability = SignalArkObservability(
        service="tests",
        alert_router=AlertRouter((sink,), clock=clock.now),
        clock=clock.now,
    )

    observability.emit(
        event_name="runtime.lease_lost",
        severity="critical",
        message="Lease lost.",
        notify=True,
        bypass_cooldown=True,
        account_id="paper_account_001",
        reason_code="LEASE_LOST_OR_EXPIRED",
    )
    observability.emit(
        event_name="runtime.lease_lost",
        severity="critical",
        message="Lease lost.",
        notify=True,
        bypass_cooldown=True,
        account_id="paper_account_001",
        reason_code="LEASE_LOST_OR_EXPIRED",
    )

    assert len(sink.events) == 2


def test_telegram_alert_sink_formats_minimum_message() -> None:
    transport = RecordingTransport()
    sink = TelegramAlertSink(
        bot_token="bot-token",
        chat_id="chat-id",
        transport=transport,
        timeout_seconds=3.0,
    )

    sink.send(
        ObservabilityEvent(
            event_name="control.kill_switch_enabled",
            severity="warning",
            timestamp=BASE_TIME,
            service="api",
            message="Kill switch enabled.",
            account_id="paper_account_001",
            symbol="600036.SH",
            control_state="kill_switch",
            reason_code="OPERATOR_REQUEST",
        )
    )

    assert len(transport.calls) == 1
    url, payload, timeout = transport.calls[0]
    assert url == "https://api.telegram.org/botbot-token/sendMessage"
    assert payload["chat_id"] == "chat-id"
    assert timeout == 3.0
    text = str(payload["text"])
    assert "control.kill_switch_enabled" in text
    assert "account_id: paper_account_001" in text
    assert "symbol: 600036.SH" in text
    assert "control_state: kill_switch" in text
    assert "reason_code: OPERATOR_REQUEST" in text
