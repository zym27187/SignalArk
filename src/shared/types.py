"""Shared domain model building blocks for SignalArk."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


def _ensure_utc(value: datetime) -> datetime:
    """Require timezone-aware datetimes and normalize them to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must be timezone-aware")
    return value.astimezone(UTC)


UtcDateTime = Annotated[datetime, AfterValidator(_ensure_utc)]
PositiveDecimal = Annotated[Decimal, Field(gt=Decimal("0"))]
NonNegativeDecimal = Annotated[Decimal, Field(ge=Decimal("0"))]
UnitIntervalDecimal = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"))]
NonEmptyStr = Annotated[str, Field(min_length=1)]
TimeframeStr = Annotated[str, Field(pattern=r"^\d+[mhdw]$")]
DomainId = UUID


class DomainModel(BaseModel):
    """Base model with shared validation conventions."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)

    @field_validator("exchange", mode="before", check_fields=False)
    @classmethod
    def normalize_exchange(cls, value: object) -> object:
        """Normalize exchange identifiers to lowercase."""
        if value is None:
            return value
        return str(value).strip().lower()

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        """Normalize trading symbols to uppercase."""
        if value is None:
            return value
        return str(value).strip().upper()

    @field_validator("asset", mode="before", check_fields=False)
    @classmethod
    def normalize_asset(cls, value: object) -> object:
        """Normalize asset codes to uppercase."""
        if value is None:
            return value
        return str(value).strip().upper()

    @field_validator("timeframe", mode="before", check_fields=False)
    @classmethod
    def normalize_timeframe(cls, value: object) -> object:
        """Normalize timeframe identifiers to lowercase."""
        if value is None:
            return value
        return str(value).strip().lower()


class DomainEntity(DomainModel):
    """Base model for domain objects with a UUID primary identifier."""

    id: DomainId = Field(default_factory=uuid4)
