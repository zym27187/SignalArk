"""Paper-state reconciliation models for Phase 9."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from src.config.settings import PaperCostModel
from src.domain.execution import Fill, Order, OrderIntent
from src.domain.portfolio import BalanceSnapshot, Position
from src.shared.types import DomainId, DomainModel, NonEmptyStr, ShanghaiDateTime, shanghai_now

IssueSeverity = Literal["warning", "critical"]


class ReplayEventFilters(DomainModel):
    """Minimal event-replay filters exposed by the diagnostics entrypoints."""

    start_time: ShanghaiDateTime | None = None
    end_time: ShanghaiDateTime | None = None
    trader_run_id: DomainId | None = None
    account_id: NonEmptyStr | None = None
    symbol: NonEmptyStr | None = None
    limit: int = Field(default=200, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_time_range(self) -> ReplayEventFilters:
        if self.start_time is not None and self.end_time is not None:
            if self.end_time < self.start_time:
                raise ValueError("end_time cannot be earlier than start_time")
        return self


class ReconciliationIssue(DomainModel):
    """One detected drift or replay failure during paper-state reconciliation."""

    code: NonEmptyStr
    severity: IssueSeverity
    object_type: NonEmptyStr
    object_id: DomainId | None = None
    account_id: NonEmptyStr
    exchange: NonEmptyStr | None = None
    symbol: NonEmptyStr | None = None
    message: NonEmptyStr
    details: dict[str, object] = Field(default_factory=dict)


class PaperReconciliationSummary(DomainModel):
    """Compact summary of one paper reconciliation pass."""

    checked_order_count: int = Field(default=0, ge=0)
    checked_fill_count: int = Field(default=0, ge=0)
    replayed_fill_count: int = Field(default=0, ge=0)
    checked_position_count: int = Field(default=0, ge=0)
    checked_balance_snapshot_count: int = Field(default=0, ge=0)
    issue_count: int = Field(default=0, ge=0)
    total_commission: Decimal = Decimal("0")
    total_transfer_fee: Decimal = Decimal("0")
    total_stamp_duty: Decimal = Decimal("0")
    total_fee: Decimal = Decimal("0")
    total_net_cash_flow: Decimal = Decimal("0")


class PaperReconciliationFacts(DomainModel):
    """Persisted paper facts consumed by the Phase 9 reconciler."""

    account_id: NonEmptyStr
    exchange: NonEmptyStr
    effective_trade_date: date
    trigger: NonEmptyStr
    order_intents: tuple[OrderIntent, ...] = ()
    orders: tuple[Order, ...] = ()
    fills: tuple[Fill, ...] = ()
    positions: tuple[Position, ...] = ()
    balance_snapshots: tuple[BalanceSnapshot, ...] = ()


class PaperReconciliationResult(DomainModel):
    """Result of comparing persisted paper facts against derived state."""

    checked_at: ShanghaiDateTime = Field(default_factory=shanghai_now)
    trigger: NonEmptyStr
    account_id: NonEmptyStr
    exchange: NonEmptyStr
    truth_source: NonEmptyStr = "local_persistent_orders_fills_positions_balance_snapshots"
    cost_model: PaperCostModel
    has_drift: bool
    issues: tuple[ReconciliationIssue, ...] = ()
    summary: PaperReconciliationSummary
