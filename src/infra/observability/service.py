"""Minimal structured-event logging and alert delivery for Phase 6C."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Protocol
from uuid import UUID

import httpx
import structlog
from pydantic import BaseModel

from src.config import Settings
from src.shared.types import shanghai_now

AlertSeverity = Literal["info", "warning", "error", "critical"]


@dataclass(frozen=True, slots=True)
class ObservabilityEvent:
    """Structured event envelope used for logs and alert payloads."""

    event_name: str
    severity: AlertSeverity
    timestamp: datetime
    service: str
    message: str | None = None
    trader_run_id: str | UUID | None = None
    instance_id: str | None = None
    account_id: str | None = None
    exchange: str | None = None
    symbol: str | None = None
    control_state: str | None = None
    reason_code: str | None = None
    signal_id: str | UUID | None = None
    order_intent_id: str | UUID | None = None
    order_id: str | UUID | None = None
    fencing_token: int | None = None
    details: Mapping[str, Any] | None = None

    def payload(self) -> dict[str, object]:
        """Return the JSON-safe payload emitted to structured logs."""
        payload = {
            "event_name": self.event_name,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "service": self.service,
            "message": self.message,
            "trader_run_id": self.trader_run_id,
            "instance_id": self.instance_id,
            "account_id": self.account_id,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "control_state": self.control_state,
            "reason_code": self.reason_code,
            "signal_id": self.signal_id,
            "order_intent_id": self.order_intent_id,
            "order_id": self.order_id,
            "fencing_token": self.fencing_token,
            "details": self.details,
        }
        return {
            key: _json_safe(value)
            for key, value in payload.items()
            if value is not None or key in {"event_name", "severity", "timestamp", "service"}
        }

    def cooldown_key(self) -> str:
        """Return the default dedupe key recommended by Phase 6C."""
        account_id = self.account_id or "-"
        symbol = self.symbol or "-"
        reason_code = self.reason_code or "-"
        return f"{self.event_name}|{account_id}|{symbol}|{reason_code}"

    def format_alert_text(self) -> str:
        """Render the minimal Telegram message body."""
        lines = [
            f"[{self.severity.upper()}] {self.event_name}",
            f"time: {self.timestamp.isoformat()}",
            f"account_id: {self.account_id or '-'}",
            f"symbol: {self.symbol or '-'}",
            f"control_state: {self.control_state or '-'}",
            f"reason_code: {self.reason_code or '-'}",
        ]
        if self.message:
            lines.append(f"message: {self.message}")
        if self.instance_id:
            lines.append(f"instance_id: {self.instance_id}")
        if self.fencing_token is not None:
            lines.append(f"fencing_token: {self.fencing_token}")
        return "\n".join(lines)


class AlertSink(Protocol):
    """Sync alert sink contract used by the lightweight observability layer."""

    name: str

    def send(self, event: ObservabilityEvent) -> None: ...


class HttpxJsonTransport(Protocol):
    """Very small HTTP transport contract to keep Telegram tests simple."""

    def post(
        self,
        url: str,
        *,
        json: Mapping[str, object],
        timeout: float,
    ) -> None: ...


class DefaultHttpxJsonTransport:
    """Default sync HTTP transport used by Telegram alert delivery."""

    def post(
        self,
        url: str,
        *,
        json: Mapping[str, object],
        timeout: float,
    ) -> None:
        response = httpx.post(url, json=json, timeout=timeout)
        response.raise_for_status()


class TelegramAlertSink:
    """Send alert events to Telegram with the minimum required message body."""

    name = "telegram"

    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        transport: HttpxJsonTransport | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._transport = transport or DefaultHttpxJsonTransport()
        self._timeout_seconds = timeout_seconds

    def send(self, event: ObservabilityEvent) -> None:
        self._transport.post(
            f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
            json={
                "chat_id": self._chat_id,
                "text": event.format_alert_text(),
                "disable_web_page_preview": True,
            },
            timeout=self._timeout_seconds,
        )


class RecordingAlertSink:
    """In-memory alert sink used by unit and integration tests."""

    name = "recording"

    def __init__(self) -> None:
        self.events: list[ObservabilityEvent] = []

    def send(self, event: ObservabilityEvent) -> None:
        self.events.append(event)


@dataclass(frozen=True, slots=True)
class AlertDispatchResult:
    """Outcome of one alert routing attempt."""

    attempted: bool
    delivered: bool
    suppressed: bool
    failures: tuple[tuple[str, str], ...]


class AlertRouter:
    """Route alert-worthy events with simple per-key cooldown."""

    def __init__(
        self,
        sinks: Sequence[AlertSink] = (),
        *,
        cooldown_seconds: int = 300,
        clock=shanghai_now,
    ) -> None:
        self._sinks = tuple(sinks)
        self._cooldown = timedelta(seconds=cooldown_seconds)
        self._clock = clock
        self._last_sent_at: dict[str, datetime] = {}

    def dispatch(
        self,
        event: ObservabilityEvent,
        *,
        bypass_cooldown: bool = False,
    ) -> AlertDispatchResult:
        if not self._sinks:
            return AlertDispatchResult(
                attempted=False,
                delivered=False,
                suppressed=False,
                failures=(),
            )

        cooldown_key = event.cooldown_key()
        now = self._clock()
        if not bypass_cooldown:
            last_sent_at = self._last_sent_at.get(cooldown_key)
            if last_sent_at is not None and now - last_sent_at < self._cooldown:
                return AlertDispatchResult(
                    attempted=True,
                    delivered=False,
                    suppressed=True,
                    failures=(),
                )

        failures: list[tuple[str, str]] = []
        delivered = False
        for sink in self._sinks:
            try:
                sink.send(event)
            except Exception as exc:  # pragma: no cover - network failure path
                failures.append((sink.name, str(exc)))
            else:
                delivered = True

        if delivered and not bypass_cooldown:
            self._last_sent_at[cooldown_key] = now

        return AlertDispatchResult(
            attempted=True,
            delivered=delivered,
            suppressed=False,
            failures=tuple(failures),
        )


class SignalArkObservability:
    """Emit structured events and optionally fan them out to alert sinks."""

    def __init__(
        self,
        *,
        service: str,
        logger_name: str | None = None,
        alert_router: AlertRouter | None = None,
        clock=shanghai_now,
    ) -> None:
        self._service = service
        self._logger = structlog.get_logger(logger_name or f"signalark.{service}.observability")
        self._alert_router = alert_router or AlertRouter(clock=clock)
        self._clock = clock
        self._series_windows: dict[str, deque[datetime]] = {}

    def emit(
        self,
        *,
        event_name: str,
        severity: AlertSeverity = "info",
        message: str | None = None,
        notify: bool = False,
        bypass_cooldown: bool = False,
        timestamp: datetime | None = None,
        trader_run_id: str | UUID | None = None,
        instance_id: str | None = None,
        account_id: str | None = None,
        exchange: str | None = None,
        symbol: str | None = None,
        control_state: str | None = None,
        reason_code: str | None = None,
        signal_id: str | UUID | None = None,
        order_intent_id: str | UUID | None = None,
        order_id: str | UUID | None = None,
        fencing_token: int | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, object]:
        event = ObservabilityEvent(
            event_name=event_name,
            severity=severity,
            timestamp=timestamp or self._clock(),
            service=self._service,
            message=message,
            trader_run_id=trader_run_id,
            instance_id=instance_id,
            account_id=account_id,
            exchange=exchange,
            symbol=symbol,
            control_state=control_state,
            reason_code=reason_code,
            signal_id=signal_id,
            order_intent_id=order_intent_id,
            order_id=order_id,
            fencing_token=fencing_token,
            details=details,
        )
        payload = event.payload()
        self._log_payload(severity, payload)

        if notify:
            result = self._alert_router.dispatch(event, bypass_cooldown=bypass_cooldown)
            if result.failures:
                self._log_payload(
                    "error",
                    {
                        "event_name": "observability.alert_delivery_failed",
                        "severity": "error",
                        "timestamp": (timestamp or self._clock()).isoformat(),
                        "service": self._service,
                        "reason_code": "ALERT_DELIVERY_FAILED",
                        "details": {
                            "original_event_name": event_name,
                            "failures": list(result.failures),
                        },
                    },
                )
        return payload

    def count_occurrence(
        self,
        *,
        series_key: str,
        window_seconds: int = 300,
        timestamp: datetime | None = None,
    ) -> int:
        """Track repeated occurrences inside a rolling time window."""
        observed_at = timestamp or self._clock()
        window = timedelta(seconds=window_seconds)
        entries = self._series_windows.setdefault(series_key, deque())
        entries.append(observed_at)
        while entries and observed_at - entries[0] > window:
            entries.popleft()
        return len(entries)

    def _log_payload(self, severity: AlertSeverity, payload: Mapping[str, object]) -> None:
        method = {
            "info": self._logger.info,
            "warning": self._logger.warning,
            "error": self._logger.error,
            "critical": self._logger.error,
        }[severity]
        method("observability_event", **dict(payload))


def build_observability(
    *,
    settings: Settings,
    service: str,
    logger_name: str | None = None,
    clock=shanghai_now,
    alert_sinks: Sequence[AlertSink] | None = None,
) -> SignalArkObservability:
    """Build the default observability service for API/trader entrypoints."""
    sinks = list(alert_sinks or ())
    if (
        settings.telegram_enabled
        and settings.telegram_bot_token
        and settings.telegram_chat_id
    ):
        sinks.append(
            TelegramAlertSink(
                bot_token=settings.telegram_bot_token,
                chat_id=settings.telegram_chat_id,
            )
        )
    return SignalArkObservability(
        service=service,
        logger_name=logger_name,
        alert_router=AlertRouter(sinks, clock=clock),
        clock=clock,
    )


def _json_safe(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump(mode="json"))
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset, deque)):
        return [_json_safe(item) for item in value]
    return str(value)
