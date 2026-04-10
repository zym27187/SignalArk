"""Minimal event-driven backtest service for Phase 8 consistency checks."""

from __future__ import annotations

import json
from bisect import bisect_right
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from hashlib import sha256
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from src.config.settings import AshareSymbolRule, PaperCostModel
from src.domain.events import BarEvent
from src.domain.execution import (
    OrderSide,
    SignalOrderIntentPlan,
    apply_order_update,
    build_signal_order_intent_plan,
    create_order_from_intent,
)
from src.domain.portfolio import BalanceSnapshot, Position, PositionStatus
from src.domain.portfolio.ledger import (
    apply_fill_event_to_portfolio,
    release_position_sellable_qty,
)
from src.domain.strategy import Signal
from src.infra.exchanges import PaperExecutionAdapter, PaperExecutionScenario, PaperFillSlice
from src.services.backtest.models import (
    BacktestCostAssumptions,
    BacktestDatasetMetadata,
    BacktestDecisionRecord,
    BacktestEquityPoint,
    BacktestPerformanceSummary,
    BacktestRunManifest,
    BacktestRunResult,
    BacktestStrategyMetadata,
)

PERCENT_QUANTUM = Decimal("0.0001")
RATIO_QUANTUM = Decimal("0.0001")
SLIPPAGE_SCALE = Decimal("10000")
FIXED_BPS_SLIPPAGE_MODEL = "bar_close_bps"
DIRECTIONAL_TIERED_SLIPPAGE_MODEL = "directional_close_tiered_bps"
SUPPORTED_SLIPPAGE_MODELS = frozenset(
    {
        FIXED_BPS_SLIPPAGE_MODEL,
        DIRECTIONAL_TIERED_SLIPPAGE_MODEL,
    }
)


class BacktestStrategyPort(Protocol):
    """Minimal strategy contract reused by both trader and backtest paths."""

    async def on_bar(self, event: BarEvent, context: object) -> Signal | None: ...


@dataclass(frozen=True, slots=True)
class BacktestStrategyContext:
    """Strategy context compatible with the runtime StrategyContext protocol."""

    trader_run_uuid: UUID
    received_at: datetime


@dataclass(slots=True)
class _MutableClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


@dataclass(slots=True)
class _OpenLot:
    qty: Decimal
    entry_bar_index: int


class BacktestService:
    """Replay finalized bars through shared strategy and order semantics."""

    def __init__(
        self,
        *,
        account_id: str,
        strategy: BacktestStrategyPort,
        symbol_rules: Mapping[str, AshareSymbolRule],
        cost_model: PaperCostModel,
        initial_cash: Decimal,
        slippage_bps: Decimal = Decimal("0"),
        slippage_model: str = FIXED_BPS_SLIPPAGE_MODEL,
    ) -> None:
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if slippage_bps < 0:
            raise ValueError("slippage_bps cannot be negative")
        if slippage_model not in SUPPORTED_SLIPPAGE_MODELS:
            raise ValueError(f"Unsupported slippage_model: {slippage_model}")

        self._account_id = account_id
        self._strategy = strategy
        self._cost_model = cost_model
        self._initial_cash = initial_cash
        self._slippage_bps = slippage_bps
        self._slippage_model = slippage_model
        self._symbol_rules = {
            str(symbol).strip().upper(): rule for symbol, rule in symbol_rules.items()
        }

    async def run(self, bars: Iterable[BarEvent]) -> BacktestRunResult:
        """Run one deterministic bar replay and return audit + performance data."""
        materialized_bars = tuple(bars)
        if not materialized_bars:
            raise ValueError("BacktestService.run requires at least one BarEvent")

        dataset = _build_dataset_metadata(materialized_bars)
        strategy_metadata = _resolve_strategy_metadata(self._strategy)
        cost_assumptions = BacktestCostAssumptions(
            commission=self._cost_model.commission,
            transfer_fee=self._cost_model.transfer_fee,
            stamp_duty_sell=self._cost_model.stamp_duty_sell,
            slippage_bps=self._slippage_bps,
            slippage_model=self._slippage_model,
            execution_constraints=_build_execution_constraints(self._slippage_model),
        )
        manifest = self._build_manifest(
            dataset=dataset,
            strategy_metadata=strategy_metadata,
            cost_assumptions=cost_assumptions,
        )

        clock = _MutableClock(value=_resolve_received_at(materialized_bars[0]))
        adapter = PaperExecutionAdapter(
            cost_model=self._cost_model,
            clock=clock.now,
            scenario_resolver=self._build_scenario,
        )
        balance = BalanceSnapshot(
            account_id=self._account_id,
            exchange=dataset.exchange,
            asset="CNY",
            total=self._initial_cash,
            available=self._initial_cash,
            locked=Decimal("0"),
            snapshot_time=materialized_bars[0].bar_start_time,
            created_at=materialized_bars[0].bar_start_time,
        )
        positions: dict[str, Position] = {}
        decisions: list[BacktestDecisionRecord] = []
        signals: list[Signal] = []
        order_intents = []
        orders = []
        fill_events = []
        seen_bar_keys: set[str] = set()
        executed_order_ids: set[UUID] = set()
        realized_trade_outcomes: list[Decimal] = []
        equity_curve: list[BacktestEquityPoint] = []
        peak_equity = self._initial_cash
        previous_event_time: datetime | None = None

        for event in materialized_bars:
            if previous_event_time is not None and event.event_time < previous_event_time:
                raise ValueError("BacktestService.run requires bars ordered by event_time")
            previous_event_time = event.event_time

            if event.symbol in positions and event.market_state is not None:
                release = release_position_sellable_qty(
                    positions[event.symbol],
                    effective_trade_date=event.market_state.trade_date,
                    released_at=event.event_time,
                )
                positions[event.symbol] = release.position

            if event.symbol in positions and positions[event.symbol].qty > 0:
                positions[event.symbol] = _mark_position_to_market(
                    positions[event.symbol],
                    mark_price=event.close,
                    marked_at=event.event_time,
                )

            if not event.actionable or event.bar_key in seen_bar_keys:
                equity_point, peak_equity = _build_equity_point(
                    bar_key=event.bar_key,
                    event_time=event.event_time,
                    balance=balance,
                    positions=positions,
                    peak_equity=peak_equity,
                )
                equity_curve.append(equity_point)
                continue

            seen_bar_keys.add(event.bar_key)
            received_at = _resolve_received_at(event)
            context = BacktestStrategyContext(
                trader_run_uuid=manifest.run_id,
                received_at=received_at,
            )
            signal = await self._strategy.on_bar(event, context)
            input_snapshot, signal_snapshot, reason_summary, skip_reason = _resolve_strategy_audit(
                strategy=self._strategy,
                event=event,
                signal=signal,
            )

            order_plan: SignalOrderIntentPlan | None = None
            persisted_order_intent = None
            final_order = None
            fill_count = 0
            if signal is None:
                skip_reason = skip_reason or "strategy_returned_none"
            else:
                signals.append(signal)
                symbol_rule = self._symbol_rules.get(signal.symbol)
                if symbol_rule is None:
                    skip_reason = "missing_symbol_rule"
                elif event.market_state is None:
                    skip_reason = "missing_market_context"
                else:
                    order_plan = build_signal_order_intent_plan(
                        signal=signal,
                        symbol_rule=symbol_rule,
                        current_position=positions.get(signal.symbol),
                        decision_price=event.decision_price,
                        market_context=event.market_state,
                    )
                    if order_plan.actionable:
                        persisted_order_intent = order_plan.to_order_intent(created_at=received_at)
                        order = create_order_from_intent(
                            persisted_order_intent,
                            submitted_at=received_at,
                        )
                        clock.value = received_at
                        execution_report = await adapter.submit_order(order, persisted_order_intent)
                        for order_update in execution_report.order_updates:
                            order = apply_order_update(order, order_update)
                        final_order = order
                        order_intents.append(persisted_order_intent)
                        orders.append(final_order)
                        if execution_report.fill_events:
                            executed_order_ids.add(final_order.id)

                        for fill_event in execution_report.fill_events:
                            portfolio_update = apply_fill_event_to_portfolio(
                                fill_event,
                                current_position=positions.get(fill_event.symbol),
                                current_balance=balance,
                            )
                            positions[fill_event.symbol] = portfolio_update.position
                            balance = portfolio_update.balance_snapshot
                            fill_events.append(fill_event)
                            fill_count += 1
                            if fill_event.fill.side is OrderSide.SELL:
                                realized_trade_outcomes.append(portfolio_update.realized_pnl_delta)

                        if signal.symbol in positions and positions[signal.symbol].qty > 0:
                            positions[signal.symbol] = _mark_position_to_market(
                                positions[signal.symbol],
                                mark_price=event.close,
                                marked_at=event.event_time,
                            )
                    else:
                        skip_reason = order_plan.skip_reason

            decisions.append(
                BacktestDecisionRecord(
                    bar_key=event.bar_key,
                    exchange=event.exchange,
                    symbol=event.symbol,
                    timeframe=event.timeframe,
                    event_time=event.event_time,
                    input_snapshot=input_snapshot,
                    signal_snapshot=signal_snapshot,
                    reason_summary=reason_summary,
                    signal=signal,
                    order_plan=(
                        {}
                        if order_plan is None
                        else _order_plan_snapshot(order_plan)
                    ),
                    order_intent=persisted_order_intent,
                    order=final_order,
                    fill_count=fill_count,
                    skip_reason=skip_reason,
                )
            )

            equity_point, peak_equity = _build_equity_point(
                bar_key=event.bar_key,
                event_time=event.event_time,
                balance=balance,
                positions=positions,
                peak_equity=peak_equity,
            )
            equity_curve.append(equity_point)

        performance = _build_performance_summary(
            initial_cash=self._initial_cash,
            signals=signals,
            orders=orders,
            fill_events=fill_events,
            executed_order_count=len(executed_order_ids),
            realized_trade_outcomes=realized_trade_outcomes,
            equity_curve=equity_curve,
        )
        return BacktestRunResult(
            manifest=manifest,
            performance=performance,
            decisions=tuple(decisions),
            signals=tuple(signals),
            order_intents=tuple(order_intents),
            orders=tuple(orders),
            fill_events=tuple(fill_events),
            equity_curve=tuple(equity_curve),
            positions=positions,
            balance=balance,
        )

    def _build_manifest(
        self,
        *,
        dataset: BacktestDatasetMetadata,
        strategy_metadata: BacktestStrategyMetadata,
        cost_assumptions: BacktestCostAssumptions,
    ) -> BacktestRunManifest:
        symbol_rules = {
            symbol: self._symbol_rules[symbol].model_dump(mode="json")
            for symbol in dataset.symbols
            if symbol in self._symbol_rules
        }
        manifest_core = {
            "account_id": self._account_id,
            "initial_cash": str(self._initial_cash),
            "strategy": strategy_metadata.model_dump(mode="json"),
            "dataset": dataset.model_dump(mode="json"),
            "cost_assumptions": cost_assumptions.model_dump(mode="json"),
            "symbol_rules": symbol_rules,
        }
        manifest_fingerprint = sha256(
            json.dumps(manifest_core, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return BacktestRunManifest(
            run_id=uuid5(NAMESPACE_URL, f"signalark:backtest:{manifest_fingerprint}"),
            account_id=self._account_id,
            initial_cash=self._initial_cash,
            strategy=strategy_metadata,
            dataset=dataset,
            cost_assumptions=cost_assumptions,
            symbol_rules=symbol_rules,
            manifest_fingerprint=manifest_fingerprint,
        )

    def _build_scenario(self, order, order_intent) -> PaperExecutionScenario:
        symbol_rule = self._symbol_rules.get(order.symbol)
        if symbol_rule is None:
            raise ValueError(f"Missing symbol rule for backtest symbol: {order.symbol}")

        reference_price = order_intent.decision_price
        if order.order_type is not None and order.order_type.value == "LIMIT":
            reference_price = order.price
        if reference_price is None:
            raise ValueError("Backtest paper scenario requires a reference price")

        market_state = order_intent.market_state
        if market_state is None:
            raise ValueError("Backtest paper scenario requires market_state")

        execution_price = _apply_simple_slippage(
            side=order.side,
            reference_price=reference_price,
            slippage_bps=self._slippage_bps,
            slippage_model=self._slippage_model,
            previous_close=market_state.previous_close,
            price_tick=symbol_rule.price_tick,
            upper_limit_price=market_state.upper_limit_price,
            lower_limit_price=market_state.lower_limit_price,
        )
        return PaperExecutionScenario(
            fill_slices=(PaperFillSlice(qty=order.qty, price=execution_price),),
        )


def _resolve_strategy_metadata(strategy: object) -> BacktestStrategyMetadata:
    payload: dict[str, object] = {}
    metadata_builder = getattr(strategy, "backtest_metadata", None)
    if callable(metadata_builder):
        raw_payload = metadata_builder()
        if isinstance(raw_payload, Mapping):
            payload = dict(raw_payload)

    strategy_id = payload.get("strategy_id")
    if strategy_id is None:
        strategy_id = getattr(strategy, "_strategy_id", type(strategy).__name__)
    description = payload.get("description")
    raw_parameters = payload.get("parameters", {})
    parameters: dict[str, str] = {}
    if isinstance(raw_parameters, Mapping):
        parameters = {str(key): str(value) for key, value in raw_parameters.items()}

    return BacktestStrategyMetadata(
        strategy_id=str(strategy_id),
        handler_name=type(strategy).__name__,
        description=None if description is None else str(description),
        parameters=parameters,
    )


def _build_dataset_metadata(bars: tuple[BarEvent, ...]) -> BacktestDatasetMetadata:
    exchange = bars[0].exchange
    timeframe = bars[0].timeframe
    for bar in bars[1:]:
        if bar.exchange != exchange:
            raise ValueError("BacktestService only supports a single exchange per run")
        if bar.timeframe != timeframe:
            raise ValueError("BacktestService only supports a single timeframe per run")

    data_fingerprint = sha256(
        json.dumps(
            [bar.model_dump(mode="json") for bar in bars],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    source_kinds = tuple(
        sorted({str(bar.source_kind) for bar in bars if bar.source_kind is not None})
    )
    symbols = tuple(sorted({bar.symbol for bar in bars}))
    return BacktestDatasetMetadata(
        exchange=exchange,
        symbols=symbols,
        timeframe=timeframe,
        bar_count=len(bars),
        start_time=bars[0].bar_start_time,
        end_time=bars[-1].bar_end_time,
        source_kinds=source_kinds,
        data_fingerprint=data_fingerprint,
    )


def _resolve_strategy_audit(
    *,
    strategy: object,
    event: BarEvent,
    signal: Signal | None,
) -> tuple[dict[str, str | None], dict[str, str] | None, str | None, str | None]:
    input_snapshot = _default_strategy_input_snapshot(event)
    signal_snapshot = None if signal is None else _default_signal_snapshot(signal)
    reason_summary = None if signal is None else signal.reason_summary
    skip_reason = None

    if signal is None:
        non_signal_builder = getattr(strategy, "build_non_signal_decision", None)
        if callable(non_signal_builder):
            non_signal_decision = non_signal_builder(event)
            if non_signal_decision is not None:
                input_snapshot = dict(non_signal_decision.audit.input_snapshot)
                signal_snapshot = dict(non_signal_decision.audit.signal_snapshot)
                reason_summary = non_signal_decision.audit.reason_summary
                skip_reason = non_signal_decision.skip_reason
        return input_snapshot, signal_snapshot, reason_summary, skip_reason

    audit_builder = getattr(strategy, "build_decision_audit", None)
    if callable(audit_builder):
        audit = audit_builder(event, signal)
        input_snapshot = dict(audit.input_snapshot)
        signal_snapshot = dict(audit.signal_snapshot)
        reason_summary = audit.reason_summary
    return input_snapshot, signal_snapshot, reason_summary, skip_reason


def _default_strategy_input_snapshot(event: BarEvent) -> dict[str, str | None]:
    market_state = event.market_state
    return {
        "bar_key": event.bar_key,
        "source_kind": event.source_kind,
        "bar_start_time": event.bar_start_time.isoformat(),
        "bar_end_time": event.bar_end_time.isoformat(),
        "close": str(event.close),
        "trade_date": market_state.trade_date.isoformat() if market_state is not None else None,
        "trading_phase": market_state.trading_phase.value if market_state is not None else None,
        "previous_close": str(market_state.previous_close) if market_state is not None else None,
    }


def _default_signal_snapshot(signal: Signal) -> dict[str, str]:
    return {
        "signal_id": str(signal.id),
        "signal_type": signal.signal_type.value,
        "target_position": str(signal.target_position),
        "event_time": signal.event_time.isoformat(),
        "created_at": signal.created_at.isoformat(),
    }


def _order_plan_snapshot(plan: SignalOrderIntentPlan) -> dict[str, object]:
    return {
        "actionable": plan.actionable,
        "side": None if plan.side is None else plan.side.value,
        "qty": str(plan.qty),
        "target_position": str(plan.target_position),
        "current_position_qty": str(plan.current_position_qty),
        "current_sellable_qty": str(plan.current_sellable_qty),
        "raw_delta_qty": str(plan.raw_delta_qty),
        "decision_price": str(plan.decision_price),
        "reduce_only": plan.reduce_only,
        "odd_lot_sell": plan.odd_lot_sell,
        "skip_reason": plan.skip_reason,
        "order_type": plan.order_type.value,
        "time_in_force": plan.time_in_force.value,
        "price": None if plan.price is None else str(plan.price),
    }


def _resolve_received_at(event: BarEvent) -> datetime:
    return max(event.event_time, event.ingest_time)


def _mark_position_to_market(
    position: Position,
    *,
    mark_price: Decimal,
    marked_at: datetime,
) -> Position:
    if position.qty == 0 or position.avg_entry_price is None:
        return position

    return position.model_copy(
        update={
            "mark_price": mark_price,
            "unrealized_pnl": (mark_price - position.avg_entry_price) * position.qty,
            "updated_at": marked_at,
            "status": PositionStatus.OPEN,
        }
    )


def _build_equity_point(
    *,
    bar_key: str,
    event_time: datetime,
    balance: BalanceSnapshot,
    positions: Mapping[str, Position],
    peak_equity: Decimal,
) -> tuple[BacktestEquityPoint, Decimal]:
    market_value = Decimal("0")
    realized_pnl = Decimal("0")
    unrealized_pnl = Decimal("0")
    open_position_count = 0
    for position in positions.values():
        realized_pnl += position.realized_pnl
        unrealized_pnl += position.unrealized_pnl
        if position.qty == 0:
            continue
        open_position_count += 1
        reference_price = (
            position.mark_price
            if position.mark_price is not None
            else position.avg_entry_price or Decimal("0")
        )
        market_value += position.qty * reference_price

    equity = balance.total + market_value
    next_peak_equity = max(peak_equity, equity)
    drawdown_ratio = Decimal("0")
    if next_peak_equity > 0:
        drawdown_ratio = (next_peak_equity - equity) / next_peak_equity
    return (
        BacktestEquityPoint(
            event_time=event_time,
            bar_key=bar_key,
            cash=balance.total,
            market_value=market_value,
            equity=equity,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            drawdown_pct=_to_pct(drawdown_ratio),
            position_count=open_position_count,
        ),
        next_peak_equity,
    )


def _build_performance_summary(
    *,
    initial_cash: Decimal,
    signals: list[Signal],
    orders: list,
    fill_events: list,
    executed_order_count: int,
    realized_trade_outcomes: list[Decimal],
    equity_curve: list[BacktestEquityPoint],
) -> BacktestPerformanceSummary:
    last_point = equity_curve[-1]
    total_return_ratio = Decimal("0")
    if initial_cash > 0:
        total_return_ratio = (last_point.equity - initial_cash) / initial_cash
    total_return_pct = _to_pct(total_return_ratio)

    winning_trade_count = sum(1 for pnl in realized_trade_outcomes if pnl > 0)
    losing_trade_count = sum(1 for pnl in realized_trade_outcomes if pnl < 0)
    turnover = sum((fill_event.fill.notional for fill_event in fill_events), Decimal("0"))
    win_rate_pct = None
    if realized_trade_outcomes:
        win_rate_pct = _to_pct(
            Decimal(winning_trade_count) / Decimal(len(realized_trade_outcomes))
        )
    max_drawdown_pct = max((point.drawdown_pct for point in equity_curve), default=Decimal("0"))
    sharpe_ratio = _compute_sharpe_ratio(equity_curve)
    return_to_drawdown_ratio = _compute_return_to_drawdown_ratio(
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
    )
    profit_factor = _compute_profit_factor(realized_trade_outcomes)
    avg_trade_pnl = _compute_average(realized_trade_outcomes)
    avg_winning_trade_pnl = _compute_average(
        [pnl for pnl in realized_trade_outcomes if pnl > 0]
    )
    avg_losing_trade_pnl = _compute_average(
        [pnl for pnl in realized_trade_outcomes if pnl < 0]
    )
    avg_holding_bars = _compute_average_holding_bars(
        fill_events=fill_events,
        equity_curve=equity_curve,
    )

    return BacktestPerformanceSummary(
        bar_count=len(equity_curve),
        signal_count=len(signals),
        order_count=len(orders),
        trade_count=executed_order_count,
        fill_count=len(fill_events),
        winning_trade_count=winning_trade_count,
        losing_trade_count=losing_trade_count,
        starting_cash=initial_cash,
        ending_cash=last_point.cash,
        ending_market_value=last_point.market_value,
        starting_equity=initial_cash,
        ending_equity=last_point.equity,
        net_pnl=last_point.equity - initial_cash,
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        realized_pnl=last_point.realized_pnl,
        unrealized_pnl=last_point.unrealized_pnl,
        turnover=turnover,
        win_rate_pct=win_rate_pct,
        sharpe_ratio=sharpe_ratio,
        return_to_drawdown_ratio=return_to_drawdown_ratio,
        profit_factor=profit_factor,
        avg_trade_pnl=avg_trade_pnl,
        avg_winning_trade_pnl=avg_winning_trade_pnl,
        avg_losing_trade_pnl=avg_losing_trade_pnl,
        avg_holding_bars=avg_holding_bars,
    )


def _apply_simple_slippage(
    *,
    side: OrderSide,
    reference_price: Decimal,
    slippage_bps: Decimal,
    slippage_model: str,
    previous_close: Decimal,
    price_tick: Decimal,
    upper_limit_price: Decimal,
    lower_limit_price: Decimal,
) -> Decimal:
    effective_slippage_bps = _resolve_effective_slippage_bps(
        side=side,
        reference_price=reference_price,
        previous_close=previous_close,
        base_slippage_bps=slippage_bps,
        slippage_model=slippage_model,
    )
    if effective_slippage_bps == 0:
        slipped_price = reference_price
    else:
        direction = Decimal("1") if side is OrderSide.BUY else Decimal("-1")
        slipped_price = reference_price * (
            Decimal("1") + ((effective_slippage_bps / SLIPPAGE_SCALE) * direction)
        )

    bounded_price = min(max(slipped_price, lower_limit_price), upper_limit_price)
    return _round_price_to_tick(
        bounded_price,
        tick_size=price_tick,
        side=side,
    )


def _round_price_to_tick(
    price: Decimal,
    *,
    tick_size: Decimal,
    side: OrderSide,
) -> Decimal:
    rounding = ROUND_UP if side is OrderSide.BUY else ROUND_DOWN
    tick_steps = (price / tick_size).to_integral_value(rounding=rounding)
    return tick_steps * tick_size


def _to_pct(ratio: Decimal) -> Decimal:
    return (ratio * Decimal("100")).quantize(PERCENT_QUANTUM)


def _resolve_effective_slippage_bps(
    *,
    side: OrderSide,
    reference_price: Decimal,
    previous_close: Decimal,
    base_slippage_bps: Decimal,
    slippage_model: str,
) -> Decimal:
    if base_slippage_bps == 0 or slippage_model == FIXED_BPS_SLIPPAGE_MODEL:
        return base_slippage_bps

    if previous_close <= 0:
        return base_slippage_bps

    move_ratio = (reference_price - previous_close) / previous_close
    adverse_move_ratio = Decimal("0")
    if side is OrderSide.BUY and move_ratio > 0:
        adverse_move_ratio = move_ratio
    elif side is OrderSide.SELL and move_ratio < 0:
        adverse_move_ratio = -move_ratio

    if adverse_move_ratio >= Decimal("0.015"):
        return base_slippage_bps * Decimal("3")
    if adverse_move_ratio >= Decimal("0.008"):
        return base_slippage_bps * Decimal("2")
    if adverse_move_ratio >= Decimal("0.003"):
        return base_slippage_bps * Decimal("1.5")
    return base_slippage_bps


def _build_execution_constraints(slippage_model: str) -> tuple[str, ...]:
    slippage_note = (
        "Slippage uses fixed bar-close bps against the decision price."
        if slippage_model == FIXED_BPS_SLIPPAGE_MODEL
        else "Slippage uses directional close tiers against previous_close and decision_price."
    )
    return (
        slippage_note,
        (
            "Backtest still assumes full fills once an order is accepted; "
            "partial fills and fill failures are not simulated."
        ),
        (
            "There is no resting order-book queue, intrabar path reconstruction, "
            "or latency competition in current backtest execution."
        ),
    )


def _quantize_ratio(value: Decimal) -> Decimal:
    return value.quantize(RATIO_QUANTUM)


def _compute_sharpe_ratio(equity_curve: list[BacktestEquityPoint]) -> Decimal | None:
    if len(equity_curve) < 3:
        return None

    bar_returns: list[Decimal] = []
    previous_equity = equity_curve[0].equity
    for point in equity_curve[1:]:
        if previous_equity > 0:
            bar_returns.append((point.equity - previous_equity) / previous_equity)
        previous_equity = point.equity

    if len(bar_returns) < 2:
        return None

    sample_size = Decimal(len(bar_returns))
    mean_return = sum(bar_returns, Decimal("0")) / sample_size
    variance = sum(
        ((bar_return - mean_return) ** 2 for bar_return in bar_returns),
        Decimal("0"),
    ) / Decimal(len(bar_returns) - 1)
    if variance <= 0:
        return None

    volatility = variance.sqrt()
    if volatility == 0:
        return None
    return _quantize_ratio((mean_return / volatility) * sample_size.sqrt())


def _compute_return_to_drawdown_ratio(
    *,
    total_return_pct: Decimal,
    max_drawdown_pct: Decimal,
) -> Decimal | None:
    if max_drawdown_pct <= 0:
        return None
    return _quantize_ratio(total_return_pct / max_drawdown_pct)


def _compute_profit_factor(realized_trade_outcomes: list[Decimal]) -> Decimal | None:
    if not realized_trade_outcomes:
        return None

    gross_profit = sum((pnl for pnl in realized_trade_outcomes if pnl > 0), Decimal("0"))
    gross_loss = -sum((pnl for pnl in realized_trade_outcomes if pnl < 0), Decimal("0"))
    if gross_loss == 0:
        if gross_profit == 0:
            return Decimal("0").quantize(RATIO_QUANTUM)
        return None
    return _quantize_ratio(gross_profit / gross_loss)


def _compute_average(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return _quantize_ratio(sum(values, Decimal("0")) / Decimal(len(values)))


def _compute_average_holding_bars(
    *,
    fill_events: list,
    equity_curve: list[BacktestEquityPoint],
) -> Decimal | None:
    if not fill_events or not equity_curve:
        return None

    bar_index_by_time: dict[datetime, int] = {}
    for index, point in enumerate(equity_curve):
        bar_index_by_time.setdefault(point.event_time, index)
    equity_times = [point.event_time for point in equity_curve]

    lots_by_symbol: dict[str, deque[_OpenLot]] = {}
    weighted_holding_bars = Decimal("0")
    closed_qty = Decimal("0")

    for fill_event in fill_events:
        bar_index = bar_index_by_time.get(fill_event.event_time)
        if bar_index is None:
            resolved_index = bisect_right(equity_times, fill_event.event_time) - 1
            if resolved_index >= 0:
                bar_index = resolved_index
        if bar_index is None:
            continue

        queue = lots_by_symbol.setdefault(fill_event.symbol, deque())
        fill = fill_event.fill
        if fill.side is OrderSide.BUY:
            queue.append(_OpenLot(qty=fill.qty, entry_bar_index=bar_index))
            continue

        remaining_qty = fill.qty
        while remaining_qty > 0 and queue:
            lot = queue[0]
            matched_qty = min(lot.qty, remaining_qty)
            weighted_holding_bars += Decimal(max(bar_index - lot.entry_bar_index, 0)) * matched_qty
            closed_qty += matched_qty
            remaining_qty -= matched_qty
            if matched_qty == lot.qty:
                queue.popleft()
            else:
                queue[0] = _OpenLot(
                    qty=lot.qty - matched_qty,
                    entry_bar_index=lot.entry_bar_index,
                )

    if closed_qty == 0:
        return None
    return _quantize_ratio(weighted_holding_bars / closed_qty)
