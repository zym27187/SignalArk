"""Audit log models used by the persistence layer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from src.shared.types import DomainId, DomainModel, NonEmptyStr, UtcDateTime, utc_now


def _to_jsonable(value: Any) -> Any:
    """Recursively normalize values into a JSON-compatible structure."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (datetime, UUID)):
        return str(value)

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, BaseModel):
        return {
            str(key): _to_jsonable(item) for key, item in value.model_dump(mode="python").items()
        }

    if isinstance(value, Mapping):
        return {str(key): _to_jsonable(item) for key, item in value.items()}

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_to_jsonable(item) for item in value]

    return str(value)


class EventLogEntry(DomainModel):
    """A persisted audit event for recovery and operator investigation."""

    id: DomainId = Field(default_factory=uuid4)
    event_id: DomainId = Field(default_factory=uuid4)
    event_type: NonEmptyStr
    source: NonEmptyStr
    trader_run_id: DomainId
    account_id: NonEmptyStr | None = None
    exchange: NonEmptyStr | None = None
    symbol: NonEmptyStr | None = None
    related_object_type: NonEmptyStr | None = None
    related_object_id: DomainId | None = None
    event_time: UtcDateTime
    ingest_time: UtcDateTime = Field(default_factory=utc_now)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: UtcDateTime = Field(default_factory=utc_now)

    @field_validator("payload_json", mode="before")
    @classmethod
    def normalize_payload(cls, value: object) -> dict[str, Any]:
        """Normalize arbitrary payloads into a JSON-like mapping."""
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise TypeError("payload_json must be a mapping")
        return _to_jsonable(value)

    @model_validator(mode="after")
    def validate_timestamps(self) -> EventLogEntry:
        """Keep event timestamps in causal order."""
        if self.ingest_time < self.event_time:
            raise ValueError("ingest_time cannot be earlier than event_time")
        if self.created_at < self.ingest_time:
            raise ValueError("created_at cannot be earlier than ingest_time")
        return self
