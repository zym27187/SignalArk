"""Pure paper-state reconciliation logic for Phase 9."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from src.config.settings import PaperCostModel
from src.domain.execution import (
    AshareExecutionCostBreakdown,
    Fill,
    FillEvent,
    Order,
    OrderSide,
    OrderStatus,
)
from src.domain.portfolio import BalanceSnapshot, Position, PositionStatus
from src.domain.portfolio.ledger import (
    PortfolioStateError,
    apply_fill_event_to_portfolio,
    release_position_sellable_qty,
)
from src.domain.reconciliation.models import (
    PaperReconciliationFacts,
    PaperReconciliationResult,
    PaperReconciliationSummary,
    ReconciliationIssue,
)
from src.shared.types import shanghai_now

FEE_QUANTUM = Decimal("0.0001")


def build_paper_cost_breakdown(
    *,
    cost_model: PaperCostModel,
    fill: Fill,
) -> AshareExecutionCostBreakdown:
    """Rebuild the deterministic paper fee/tax breakdown from one persisted fill."""
    gross_notional = fill.notional
    commission = _quantize_fee(gross_notional * cost_model.commission)
    transfer_fee = _quantize_fee(gross_notional * cost_model.transfer_fee)
    stamp_duty = Decimal("0")
    if fill.side is OrderSide.SELL:
        stamp_duty = _quantize_fee(gross_notional * cost_model.stamp_duty_sell)

    total_fee = commission + transfer_fee + stamp_duty
    net_cash_flow = (
        gross_notional - total_fee if fill.side is OrderSide.SELL else -(gross_notional + total_fee)
    )
    return AshareExecutionCostBreakdown(
        gross_notional=gross_notional,
        commission=commission,
        transfer_fee=transfer_fee,
        stamp_duty=stamp_duty,
        total_fee=total_fee,
        net_cash_flow=net_cash_flow,
    )


def build_replayed_fill_event(
    *,
    fill: Fill,
    order: Order,
    cost_model: PaperCostModel,
) -> FillEvent:
    """Build the fill envelope needed to replay a persisted fill through the ledger."""
    return FillEvent(
        order_id=fill.order_id,
        order_intent_id=order.order_intent_id,
        trader_run_id=fill.trader_run_id,
        account_id=fill.account_id,
        exchange=fill.exchange,
        symbol=fill.symbol,
        fill=fill,
        cost_breakdown=build_paper_cost_breakdown(cost_model=cost_model, fill=fill),
        event_time=fill.fill_time,
        created_at=fill.created_at,
    )


def reconcile_paper_state(
    *,
    facts: PaperReconciliationFacts,
    cost_model: PaperCostModel,
    checked_at: datetime | None = None,
) -> PaperReconciliationResult:
    """Recompute paper positions/balances from persisted facts and flag drift."""
    observed_at = checked_at or shanghai_now()
    issues: list[ReconciliationIssue] = []
    order_intents_by_id = {intent.id: intent for intent in facts.order_intents}
    orders_by_id = {order.id: order for order in facts.orders}
    fills_by_order_id: dict[object, list[Fill]] = defaultdict(list)
    for fill in facts.fills:
        fills_by_order_id[fill.order_id].append(fill)

    for fill_list in fills_by_order_id.values():
        fill_list.sort(key=lambda fill: (fill.fill_time, fill.created_at, fill.id))

    _check_orders(
        facts=facts,
        order_intents_by_id=order_intents_by_id,
        fills_by_order_id=fills_by_order_id,
        issues=issues,
    )

    latest_balances_by_asset: dict[str, BalanceSnapshot] = {}
    baseline_balances_by_asset: dict[str, BalanceSnapshot] = {}
    for snapshot in sorted(
        facts.balance_snapshots,
        key=lambda item: (item.asset, item.snapshot_time, item.created_at, item.id),
    ):
        latest_balances_by_asset[snapshot.asset] = snapshot
        baseline_balances_by_asset.setdefault(snapshot.asset, snapshot)

    replayed_positions: dict[str, Position] = {}
    replayed_balances: dict[str, BalanceSnapshot] = dict(baseline_balances_by_asset)
    total_commission = Decimal("0")
    total_transfer_fee = Decimal("0")
    total_stamp_duty = Decimal("0")
    total_fee = Decimal("0")
    total_net_cash_flow = Decimal("0")
    replayed_fill_count = 0

    for fill in sorted(facts.fills, key=lambda item: (item.fill_time, item.created_at, item.id)):
        cost_breakdown = build_paper_cost_breakdown(cost_model=cost_model, fill=fill)
        total_commission += cost_breakdown.commission
        total_transfer_fee += cost_breakdown.transfer_fee
        total_stamp_duty += cost_breakdown.stamp_duty
        total_fee += cost_breakdown.total_fee
        total_net_cash_flow += cost_breakdown.net_cash_flow

        if fill.fee != cost_breakdown.total_fee:
            issues.append(
                _issue(
                    code="FILL_FEE_DRIFT",
                    object_type="fill",
                    object_id=fill.id,
                    account_id=fill.account_id,
                    exchange=fill.exchange,
                    symbol=fill.symbol,
                    message="Persisted fill fee does not match the deterministic paper cost model.",
                    details={
                        "persisted_fee": fill.fee,
                        "expected_total_fee": cost_breakdown.total_fee,
                        "expected_commission": cost_breakdown.commission,
                        "expected_transfer_fee": cost_breakdown.transfer_fee,
                        "expected_stamp_duty": cost_breakdown.stamp_duty,
                    },
                )
            )

        order = orders_by_id.get(fill.order_id)
        if order is None:
            issues.append(
                _issue(
                    code="FILL_ORDER_MISSING",
                    object_type="fill",
                    object_id=fill.id,
                    account_id=fill.account_id,
                    exchange=fill.exchange,
                    symbol=fill.symbol,
                    message="Fill replay could not find its persisted order.",
                    details={"order_id": fill.order_id},
                )
            )
            continue

        try:
            fill_event = build_replayed_fill_event(
                fill=fill,
                order=order,
                cost_model=cost_model,
            )
            portfolio_update = apply_fill_event_to_portfolio(
                fill_event,
                current_position=replayed_positions.get(fill.symbol),
                current_balance=replayed_balances.get(fill_event.cost_breakdown.currency),
            )
        except (PortfolioStateError, ValueError) as exc:
            issues.append(
                _issue(
                    code="FILL_LEDGER_REPLAY_FAILED",
                    object_type="fill",
                    object_id=fill.id,
                    account_id=fill.account_id,
                    exchange=fill.exchange,
                    symbol=fill.symbol,
                    message="Persisted fill could not be replayed onto the paper ledger.",
                    details={"error": str(exc), "order_id": fill.order_id},
                )
            )
            continue

        replayed_positions[fill.symbol] = portfolio_update.position
        replayed_balances[portfolio_update.balance_snapshot.asset] = (
            portfolio_update.balance_snapshot
        )
        replayed_fill_count += 1

    replayed_positions = {
        symbol: release_position_sellable_qty(
            position,
            effective_trade_date=facts.effective_trade_date,
            released_at=observed_at,
        ).position
        for symbol, position in replayed_positions.items()
    }

    _check_positions(
        facts=facts,
        replayed_positions=replayed_positions,
        issues=issues,
    )
    _check_balances(
        facts=facts,
        replayed_balances=replayed_balances,
        latest_balances_by_asset=latest_balances_by_asset,
        issues=issues,
    )

    summary = PaperReconciliationSummary(
        checked_order_count=len(facts.orders),
        checked_fill_count=len(facts.fills),
        replayed_fill_count=replayed_fill_count,
        checked_position_count=len(facts.positions),
        checked_balance_snapshot_count=len(facts.balance_snapshots),
        issue_count=len(issues),
        total_commission=total_commission,
        total_transfer_fee=total_transfer_fee,
        total_stamp_duty=total_stamp_duty,
        total_fee=total_fee,
        total_net_cash_flow=total_net_cash_flow,
    )
    return PaperReconciliationResult(
        checked_at=observed_at,
        trigger=facts.trigger,
        account_id=facts.account_id,
        exchange=facts.exchange,
        cost_model=cost_model,
        has_drift=bool(issues),
        issues=tuple(issues),
        summary=summary,
    )


def _check_orders(
    *,
    facts: PaperReconciliationFacts,
    order_intents_by_id: dict[object, object],
    fills_by_order_id: dict[object, list[Fill]],
    issues: list[ReconciliationIssue],
) -> None:
    for order in facts.orders:
        order_intent = order_intents_by_id.get(order.order_intent_id)
        if order_intent is None:
            issues.append(
                _issue(
                    code="ORDER_INTENT_MISSING",
                    object_type="order",
                    object_id=order.id,
                    account_id=order.account_id,
                    exchange=order.exchange,
                    symbol=order.symbol,
                    message="Persisted order has no matching order_intent metadata.",
                    details={"order_intent_id": order.order_intent_id},
                )
            )
        else:
            mismatched_fields = {
                field_name: {
                    "persisted_order": getattr(order, field_name),
                    "order_intent": getattr(order_intent, field_name),
                }
                for field_name in (
                    "account_id",
                    "exchange",
                    "symbol",
                    "side",
                    "order_type",
                    "time_in_force",
                    "qty",
                    "price",
                )
                if getattr(order, field_name) != getattr(order_intent, field_name)
            }
            if mismatched_fields:
                issues.append(
                    _issue(
                        code="ORDER_INTENT_DRIFT",
                        object_type="order",
                        object_id=order.id,
                        account_id=order.account_id,
                        exchange=order.exchange,
                        symbol=order.symbol,
                        message="Persisted order fields drifted away from their order_intent.",
                        details={
                            "order_intent_id": order.order_intent_id,
                            "mismatched_fields": mismatched_fields,
                        },
                    )
                )

        fills = fills_by_order_id.get(order.id, [])
        total_fill_qty = sum((fill.qty for fill in fills), start=Decimal("0"))
        if total_fill_qty != order.filled_qty:
            issues.append(
                _issue(
                    code="ORDER_FILLED_QTY_DRIFT",
                    object_type="order",
                    object_id=order.id,
                    account_id=order.account_id,
                    exchange=order.exchange,
                    symbol=order.symbol,
                    message="Persisted order.filled_qty does not match the sum of persisted fills.",
                    details={
                        "order_filled_qty": order.filled_qty,
                        "replayed_fill_qty": total_fill_qty,
                    },
                )
            )

        if total_fill_qty > order.qty:
            issues.append(
                _issue(
                    code="ORDER_OVERFILLED",
                    object_type="order",
                    object_id=order.id,
                    account_id=order.account_id,
                    exchange=order.exchange,
                    symbol=order.symbol,
                    message="Persisted fills exceed the order quantity.",
                    details={"order_qty": order.qty, "replayed_fill_qty": total_fill_qty},
                )
            )

        if total_fill_qty > 0:
            weighted_notional = sum((fill.notional for fill in fills), start=Decimal("0"))
            expected_avg_fill_price = weighted_notional / total_fill_qty
            if order.avg_fill_price != expected_avg_fill_price:
                issues.append(
                    _issue(
                        code="ORDER_AVG_FILL_PRICE_DRIFT",
                        object_type="order",
                        object_id=order.id,
                        account_id=order.account_id,
                        exchange=order.exchange,
                        symbol=order.symbol,
                        message=(
                            "Persisted order.avg_fill_price does not match "
                            "the weighted fill price."
                        ),
                        details={
                            "order_avg_fill_price": order.avg_fill_price,
                            "expected_avg_fill_price": expected_avg_fill_price,
                        },
                    )
                )

        expected_status: OrderStatus | None = None
        if total_fill_qty == 0:
            if order.status in {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED}:
                expected_status = OrderStatus.ACK
        elif total_fill_qty == order.qty:
            if order.status is not OrderStatus.FILLED:
                expected_status = OrderStatus.FILLED
        elif order.status not in {OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELED}:
            expected_status = OrderStatus.PARTIALLY_FILLED

        if expected_status is not None:
            issues.append(
                _issue(
                    code="ORDER_STATUS_DRIFT",
                    object_type="order",
                    object_id=order.id,
                    account_id=order.account_id,
                    exchange=order.exchange,
                    symbol=order.symbol,
                    message="Persisted order status is inconsistent with its fill history.",
                    details={
                        "order_status": order.status,
                        "expected_status": expected_status,
                        "replayed_fill_qty": total_fill_qty,
                    },
                )
            )


def _check_positions(
    *,
    facts: PaperReconciliationFacts,
    replayed_positions: dict[str, Position],
    issues: list[ReconciliationIssue],
) -> None:
    persisted_positions = {position.symbol: position for position in facts.positions}
    for symbol in sorted(set(persisted_positions) | set(replayed_positions)):
        persisted = persisted_positions.get(symbol)
        replayed = replayed_positions.get(symbol)
        if replayed is None:
            if persisted is None:
                continue
            if (
                persisted.qty != 0
                or persisted.sellable_qty != 0
                or persisted.status is not PositionStatus.CLOSED
                or persisted.avg_entry_price is not None
                or persisted.mark_price is not None
                or persisted.unrealized_pnl != 0
            ):
                issues.append(
                    _issue(
                        code="POSITION_UNBACKED_BY_FILLS",
                        object_type="position",
                        object_id=persisted.id,
                        account_id=persisted.account_id,
                        exchange=persisted.exchange,
                        symbol=persisted.symbol,
                        message="Persisted position has no matching replayed fill-backed state.",
                        details={"persisted_position": persisted.model_dump(mode="json")},
                    )
                )
            continue

        if persisted is None:
            issues.append(
                _issue(
                    code="POSITION_MISSING",
                    object_type="position",
                    account_id=replayed.account_id,
                    exchange=replayed.exchange,
                    symbol=replayed.symbol,
                    message="Replay derived an open position that is missing from persistence.",
                    details={"expected_position": replayed.model_dump(mode="json")},
                )
            )
            continue

        mismatched_fields = {
            field_name: {
                "persisted": getattr(persisted, field_name),
                "expected": getattr(replayed, field_name),
            }
            for field_name in (
                "qty",
                "sellable_qty",
                "avg_entry_price",
                "mark_price",
                "unrealized_pnl",
                "realized_pnl",
                "status",
            )
            if getattr(persisted, field_name) != getattr(replayed, field_name)
        }
        if mismatched_fields:
            issues.append(
                _issue(
                    code="POSITION_STATE_DRIFT",
                    object_type="position",
                    object_id=persisted.id,
                    account_id=persisted.account_id,
                    exchange=persisted.exchange,
                    symbol=persisted.symbol,
                    message="Persisted position state drifted from the replayed paper ledger.",
                    details={"mismatched_fields": mismatched_fields},
                )
            )


def _check_balances(
    *,
    facts: PaperReconciliationFacts,
    replayed_balances: dict[str, BalanceSnapshot],
    latest_balances_by_asset: dict[str, BalanceSnapshot],
    issues: list[ReconciliationIssue],
) -> None:
    for asset in sorted(set(latest_balances_by_asset) | set(replayed_balances)):
        persisted = latest_balances_by_asset.get(asset)
        replayed = replayed_balances.get(asset)
        if replayed is None and persisted is None:
            continue
        if replayed is None and persisted is not None:
            issues.append(
                _issue(
                    code="BALANCE_UNBACKED_BY_LEDGER",
                    object_type="balance_snapshot",
                    object_id=persisted.id,
                    account_id=persisted.account_id,
                    exchange=persisted.exchange,
                    message="Persisted balance snapshot has no replayed balance state.",
                    details={
                        "asset": asset,
                        "persisted_balance": persisted.model_dump(mode="json"),
                    },
                )
            )
            continue
        if replayed is not None and persisted is None:
            issues.append(
                _issue(
                    code="BALANCE_SNAPSHOT_MISSING",
                    object_type="balance_snapshot",
                    account_id=replayed.account_id,
                    exchange=replayed.exchange,
                    message=(
                        "Replayed balance state is missing its latest "
                        "persisted balance snapshot."
                    ),
                    details={"asset": asset, "expected_balance": replayed.model_dump(mode="json")},
                )
            )
            continue

        assert replayed is not None and persisted is not None
        mismatched_fields = {
            field_name: {
                "persisted": getattr(persisted, field_name),
                "expected": getattr(replayed, field_name),
            }
            for field_name in ("total", "available", "locked")
            if getattr(persisted, field_name) != getattr(replayed, field_name)
        }
        if mismatched_fields:
            issues.append(
                _issue(
                    code="BALANCE_STATE_DRIFT",
                    object_type="balance_snapshot",
                    object_id=persisted.id,
                    account_id=persisted.account_id,
                    exchange=persisted.exchange,
                    message=(
                        "Persisted latest balance snapshot drifted from "
                        "replayed ledger cash state."
                    ),
                    details={"asset": asset, "mismatched_fields": mismatched_fields},
                )
            )
        if persisted.snapshot_time < replayed.snapshot_time:
            issues.append(
                _issue(
                    code="BALANCE_SNAPSHOT_STALE",
                    object_type="balance_snapshot",
                    object_id=persisted.id,
                    account_id=persisted.account_id,
                    exchange=persisted.exchange,
                    message=(
                        "Latest persisted balance snapshot is older than "
                        "the replayed ledger state."
                    ),
                    details={
                        "asset": asset,
                        "persisted_snapshot_time": persisted.snapshot_time,
                        "expected_snapshot_time": replayed.snapshot_time,
                    },
                )
            )


def _issue(
    *,
    code: str,
    object_type: str,
    account_id: str,
    message: str,
    severity: str = "critical",
    object_id=None,
    exchange: str | None = None,
    symbol: str | None = None,
    details: dict[str, object] | None = None,
) -> ReconciliationIssue:
    return ReconciliationIssue(
        code=code,
        severity=severity,
        object_type=object_type,
        object_id=object_id,
        account_id=account_id,
        exchange=exchange,
        symbol=symbol,
        message=message,
        details=details or {},
    )


def _quantize_fee(value: Decimal) -> Decimal:
    return value.quantize(FEE_QUANTUM, rounding=ROUND_HALF_UP)
