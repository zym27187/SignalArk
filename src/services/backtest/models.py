"""Minimal backtest models for Phase 8 event-driven research runs."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import Field

from src.domain.execution import FillEvent, Order, OrderIntent
from src.domain.portfolio import BalanceSnapshot, Position
from src.domain.strategy import Signal
from src.shared.types import (
    DomainModel,
    NonEmptyStr,
    NonNegativeDecimal,
    PositiveDecimal,
    ShanghaiDateTime,
    TimeframeStr,
)


class BacktestStrategyMetadata(DomainModel):
    """Reproducible description of the strategy used in one run."""

    strategy_id: NonEmptyStr
    handler_name: NonEmptyStr
    description: str | None = None
    parameters: dict[str, str] = Field(default_factory=dict)


class BacktestDatasetMetadata(DomainModel):
    """Minimal dataset identity used to reproduce a backtest run."""

    exchange: NonEmptyStr
    symbols: tuple[NonEmptyStr, ...]
    timeframe: TimeframeStr
    bar_count: int = Field(ge=1)
    start_time: ShanghaiDateTime
    end_time: ShanghaiDateTime
    source_kinds: tuple[NonEmptyStr, ...] = ()
    data_fingerprint: NonEmptyStr


class BacktestCostAssumptions(DomainModel):
    """Cost and execution assumptions applied by the minimal backtester."""

    commission: NonNegativeDecimal
    transfer_fee: NonNegativeDecimal
    stamp_duty_sell: NonNegativeDecimal
    slippage_bps: NonNegativeDecimal = Decimal("0")
    fee_model: NonEmptyStr = "ashare_paper_cost_model"
    slippage_model: NonEmptyStr = "bar_close_bps"
    partial_fill_model: NonEmptyStr = "full_fill_only"
    unfilled_qty_handling: NonEmptyStr = "not_applicable_full_fill"
    execution_constraints: tuple[NonEmptyStr, ...] = ()


class BacktestRunManifest(DomainModel):
    """Serializable metadata that makes a run reproducible."""

    schema_version: NonEmptyStr = "phase8.minimum.v1"
    run_id: UUID
    account_id: NonEmptyStr
    initial_cash: PositiveDecimal
    strategy: BacktestStrategyMetadata
    dataset: BacktestDatasetMetadata
    cost_assumptions: BacktestCostAssumptions
    symbol_rules: dict[str, dict[str, Any]]
    manifest_fingerprint: NonEmptyStr


class BacktestDecisionRecord(DomainModel):
    """Audit trail for one bar-driven strategy decision."""

    bar_key: NonEmptyStr
    exchange: NonEmptyStr
    symbol: NonEmptyStr
    timeframe: TimeframeStr
    event_time: ShanghaiDateTime
    input_snapshot: dict[str, str | None] = Field(default_factory=dict)
    signal_snapshot: dict[str, str] | None = None
    reason_summary: str | None = None
    audit_summary: dict[str, str | bool | None] | None = None
    signal: Signal | None = None
    order_plan: dict[str, Any] = Field(default_factory=dict)
    order_intent: OrderIntent | None = None
    order: Order | None = None
    fill_count: int = Field(default=0, ge=0)
    skip_reason: str | None = None


class BacktestEquityPoint(DomainModel):
    """One point on the end-of-bar equity curve."""

    event_time: ShanghaiDateTime
    bar_key: NonEmptyStr
    cash: NonNegativeDecimal
    market_value: NonNegativeDecimal
    equity: NonNegativeDecimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    drawdown_pct: NonNegativeDecimal = Decimal("0")
    position_count: int = Field(ge=0)


class BacktestPerformanceSummary(DomainModel):
    """Standard minimal performance metrics for a Phase 8 run."""

    bar_count: int = Field(ge=0)
    signal_count: int = Field(ge=0)
    order_count: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    fill_count: int = Field(ge=0)
    winning_trade_count: int = Field(default=0, ge=0)
    losing_trade_count: int = Field(default=0, ge=0)
    starting_cash: NonNegativeDecimal
    ending_cash: NonNegativeDecimal
    ending_market_value: NonNegativeDecimal
    starting_equity: NonNegativeDecimal
    ending_equity: NonNegativeDecimal
    net_pnl: Decimal
    total_return_pct: Decimal
    max_drawdown_pct: NonNegativeDecimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    turnover: NonNegativeDecimal = Decimal("0")
    win_rate_pct: NonNegativeDecimal | None = None
    sharpe_ratio: Decimal | None = None
    return_to_drawdown_ratio: Decimal | None = None
    profit_factor: Decimal | None = None
    avg_trade_pnl: Decimal | None = None
    avg_winning_trade_pnl: Decimal | None = None
    avg_losing_trade_pnl: Decimal | None = None
    avg_holding_bars: Decimal | None = None


class BacktestRunResult(DomainModel):
    """Complete result payload for one minimal backtest run."""

    manifest: BacktestRunManifest
    performance: BacktestPerformanceSummary
    decisions: tuple[BacktestDecisionRecord, ...] = ()
    signals: tuple[Signal, ...] = ()
    order_intents: tuple[OrderIntent, ...] = ()
    orders: tuple[Order, ...] = ()
    fill_events: tuple[FillEvent, ...] = ()
    equity_curve: tuple[BacktestEquityPoint, ...] = ()
    positions: dict[str, Position] = Field(default_factory=dict)
    balance: BalanceSnapshot
