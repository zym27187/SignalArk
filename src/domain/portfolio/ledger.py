"""Portfolio ledger helpers for fill-driven position and balance updates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from src.domain.execution import FillEvent, OrderSide
from src.domain.portfolio.models import BalanceSnapshot, Position, PositionStatus


class PortfolioStateError(ValueError):
    """Raised when a fill cannot be reconciled onto the current portfolio state."""


@dataclass(frozen=True, slots=True)
class SellableQtyRelease:
    """Result of applying the A-share T+1 sellable-quantity release rule."""

    position: Position
    released_qty: Decimal = Decimal("0")

    @property
    def applied(self) -> bool:
        """Return whether any previously locked quantity became sellable."""
        return self.released_qty > 0


@dataclass(frozen=True, slots=True)
class PortfolioFillUpdate:
    """The new portfolio state produced by applying one fill event."""

    position: Position
    balance_snapshot: BalanceSnapshot
    released_sellable_qty: Decimal
    realized_pnl_delta: Decimal
    cash_delta: Decimal


def release_position_sellable_qty(
    position: Position,
    *,
    effective_trade_date: date,
    released_at: datetime,
) -> SellableQtyRelease:
    """Release previously locked T+1 quantity once the trade date advances."""
    if (
        position.qty == 0
        or position.sellable_qty == position.qty
        or position.updated_at.date() >= effective_trade_date
    ):
        return SellableQtyRelease(position=position)

    released_qty = position.qty - position.sellable_qty
    released_position = position.model_copy(
        update={
            "sellable_qty": position.qty,
            "updated_at": released_at,
        }
    )
    return SellableQtyRelease(
        position=released_position,
        released_qty=released_qty,
    )


def apply_fill_event_to_portfolio(
    fill_event: FillEvent,
    *,
    current_position: Position | None,
    current_balance: BalanceSnapshot | None,
) -> PortfolioFillUpdate:
    """Apply one normalized fill onto the latest persisted position and balance."""
    fill = fill_event.fill
    released_sellable_qty = Decimal("0")
    position_before = current_position

    if current_position is not None:
        _validate_position_matches_fill(position=current_position, fill_event=fill_event)
        release = release_position_sellable_qty(
            current_position,
            effective_trade_date=fill_event.event_time.date(),
            released_at=fill_event.event_time,
        )
        position_before = release.position
        released_sellable_qty = release.released_qty

    if fill.side is OrderSide.BUY:
        next_position, realized_pnl_delta = _apply_buy_fill(
            fill_event=fill_event,
            current_position=position_before,
        )
    else:
        next_position, realized_pnl_delta = _apply_sell_fill(
            fill_event=fill_event,
            current_position=position_before,
        )

    next_balance = _apply_cash_flow(
        fill_event=fill_event,
        current_balance=current_balance,
    )
    return PortfolioFillUpdate(
        position=next_position,
        balance_snapshot=next_balance,
        released_sellable_qty=released_sellable_qty,
        realized_pnl_delta=realized_pnl_delta,
        cash_delta=fill_event.cost_breakdown.net_cash_flow,
    )


def _apply_buy_fill(
    *,
    fill_event: FillEvent,
    current_position: Position | None,
) -> tuple[Position, Decimal]:
    fill = fill_event.fill
    total_fee = fill_event.cost_breakdown.total_fee
    previous_qty = Decimal("0")
    previous_sellable_qty = Decimal("0")
    previous_avg_entry_price = Decimal("0")
    previous_realized_pnl = Decimal("0")

    if current_position is not None:
        previous_qty = current_position.qty
        previous_sellable_qty = current_position.sellable_qty
        previous_realized_pnl = current_position.realized_pnl
        if current_position.avg_entry_price is not None:
            previous_avg_entry_price = current_position.avg_entry_price

    new_qty = previous_qty + fill.qty
    carried_cost = (previous_qty * previous_avg_entry_price) + fill.notional
    avg_entry_price = carried_cost / new_qty
    mark_price = fill.price
    realized_pnl = previous_realized_pnl - total_fee
    unrealized_pnl = (mark_price - avg_entry_price) * new_qty

    position_payload = {
        "account_id": fill.account_id,
        "exchange": fill.exchange,
        "symbol": fill.symbol,
        "qty": new_qty,
        "sellable_qty": previous_sellable_qty,
        "avg_entry_price": avg_entry_price,
        "mark_price": mark_price,
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl": realized_pnl,
        "status": PositionStatus.OPEN,
        "updated_at": fill_event.event_time,
    }
    if current_position is not None:
        position_payload["id"] = current_position.id
        position_payload["side"] = current_position.side

    return Position(**position_payload), -total_fee


def _apply_sell_fill(
    *,
    fill_event: FillEvent,
    current_position: Position | None,
) -> tuple[Position, Decimal]:
    if (
        current_position is None
        or current_position.qty == 0
        or current_position.avg_entry_price is None
    ):
        raise PortfolioStateError("SELL fills require an existing open position")

    fill = fill_event.fill
    if fill.qty > current_position.qty:
        raise PortfolioStateError("SELL fill qty cannot exceed the current position qty")
    if fill.qty > current_position.sellable_qty:
        raise PortfolioStateError("SELL fill qty cannot exceed the current sellable_qty")

    total_fee = fill_event.cost_breakdown.total_fee
    realized_pnl_delta = (
        (fill.price - current_position.avg_entry_price) * fill.qty
    ) - total_fee
    remaining_qty = current_position.qty - fill.qty
    remaining_sellable_qty = current_position.sellable_qty - fill.qty
    realized_pnl = current_position.realized_pnl + realized_pnl_delta

    if remaining_qty == 0:
        return (
            Position(
                id=current_position.id,
                account_id=current_position.account_id,
                exchange=current_position.exchange,
                symbol=current_position.symbol,
                side=current_position.side,
                qty=Decimal("0"),
                sellable_qty=Decimal("0"),
                avg_entry_price=None,
                mark_price=None,
                unrealized_pnl=Decimal("0"),
                realized_pnl=realized_pnl,
                status=PositionStatus.CLOSED,
                updated_at=fill_event.event_time,
            ),
            realized_pnl_delta,
        )

    return (
        Position(
            id=current_position.id,
            account_id=current_position.account_id,
            exchange=current_position.exchange,
            symbol=current_position.symbol,
            side=current_position.side,
            qty=remaining_qty,
            sellable_qty=remaining_sellable_qty,
            avg_entry_price=current_position.avg_entry_price,
            mark_price=fill.price,
            unrealized_pnl=(fill.price - current_position.avg_entry_price) * remaining_qty,
            realized_pnl=realized_pnl,
            status=PositionStatus.OPEN,
            updated_at=fill_event.event_time,
        ),
        realized_pnl_delta,
    )


def _apply_cash_flow(
    *,
    fill_event: FillEvent,
    current_balance: BalanceSnapshot | None,
) -> BalanceSnapshot:
    currency = fill_event.cost_breakdown.currency
    cash_delta = fill_event.cost_breakdown.net_cash_flow

    total = Decimal("0")
    available = Decimal("0")
    locked = Decimal("0")
    if current_balance is not None:
        _validate_balance_matches_fill(balance=current_balance, fill_event=fill_event)
        if current_balance.asset != currency:
            raise PortfolioStateError("Balance asset must match the fill-event settlement currency")
        total = current_balance.total
        available = current_balance.available
        locked = current_balance.locked
    elif cash_delta < 0:
        raise PortfolioStateError(
            "BUY fills require an existing balance snapshot before cash can be debited"
        )

    next_total = total + cash_delta
    next_available = available + cash_delta
    if next_total < 0 or next_available < 0:
        raise PortfolioStateError("Balance update would produce a negative cash state")

    return BalanceSnapshot(
        account_id=fill_event.account_id,
        exchange=fill_event.exchange,
        asset=currency,
        total=next_total,
        available=next_available,
        locked=locked,
        snapshot_time=fill_event.event_time,
        created_at=fill_event.event_time,
    )


def _validate_position_matches_fill(*, position: Position, fill_event: FillEvent) -> None:
    if position.account_id != fill_event.account_id:
        raise PortfolioStateError("position.account_id must match fill_event.account_id")
    if position.exchange != fill_event.exchange:
        raise PortfolioStateError("position.exchange must match fill_event.exchange")
    if position.symbol != fill_event.symbol:
        raise PortfolioStateError("position.symbol must match fill_event.symbol")


def _validate_balance_matches_fill(*, balance: BalanceSnapshot, fill_event: FillEvent) -> None:
    if balance.account_id != fill_event.account_id:
        raise PortfolioStateError("balance.account_id must match fill_event.account_id")
    if balance.exchange != fill_event.exchange:
        raise PortfolioStateError("balance.exchange must match fill_event.exchange")
