from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from src.domain.execution import (
    AshareExecutionCostBreakdown,
    Fill,
    FillEvent,
    LiquidityType,
    OrderSide,
)
from src.domain.portfolio import BalanceSnapshot, Position, PositionStatus
from src.domain.portfolio.ledger import (
    apply_fill_event_to_portfolio,
    release_position_sellable_qty,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 1, 11, 0, tzinfo=SHANGHAI)
TRADER_RUN_ID = UUID("91919191-9191-4191-8191-919191919191")
ORDER_ID = UUID("82828282-8282-4282-8282-828282828282")


def _position(
    *,
    qty: Decimal,
    sellable_qty: Decimal,
    updated_at: datetime,
    avg_entry_price: Decimal | None = None,
    realized_pnl: Decimal = Decimal("0"),
    mark_price: Decimal | None = None,
) -> Position:
    return Position(
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        qty=qty,
        sellable_qty=sellable_qty,
        avg_entry_price=avg_entry_price,
        mark_price=mark_price,
        unrealized_pnl=Decimal("0")
        if qty == 0 or avg_entry_price is None or mark_price is None
        else (mark_price - avg_entry_price) * qty,
        realized_pnl=realized_pnl,
        status=PositionStatus.OPEN if qty > 0 else PositionStatus.CLOSED,
        updated_at=updated_at,
    )


def _balance_snapshot(*, total: Decimal, available: Decimal, locked: Decimal) -> BalanceSnapshot:
    return BalanceSnapshot(
        account_id="paper_account_001",
        exchange="cn_equity",
        asset="CNY",
        total=total,
        available=available,
        locked=locked,
        snapshot_time=BASE_TIME - timedelta(minutes=5),
        created_at=BASE_TIME - timedelta(minutes=5),
    )


def _fill_event(
    *,
    side: OrderSide,
    qty: Decimal,
    price: Decimal,
    fee: Decimal,
    commission: Decimal,
    transfer_fee: Decimal,
    stamp_duty: Decimal,
    net_cash_flow: Decimal,
    event_time: datetime,
) -> FillEvent:
    fill = Fill(
        id=UUID("73737373-7373-4373-8373-737373737373"),
        order_id=ORDER_ID,
        trader_run_id=TRADER_RUN_ID,
        exchange_fill_id=f"paper-fill-{side.value.lower()}",
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        side=side,
        qty=qty,
        price=price,
        fee=fee,
        fee_asset="CNY",
        liquidity_type=LiquidityType.TAKER,
        fill_time=event_time,
        created_at=event_time,
    )
    return FillEvent(
        id=UUID("62626262-6262-4262-8262-626262626262"),
        order_id=ORDER_ID,
        order_intent_id=UUID("51515151-5151-4151-8151-515151515151"),
        trader_run_id=TRADER_RUN_ID,
        account_id="paper_account_001",
        exchange="cn_equity",
        symbol="600036.SH",
        fill=fill,
        cost_breakdown=AshareExecutionCostBreakdown(
            gross_notional=qty * price,
            commission=commission,
            transfer_fee=transfer_fee,
            stamp_duty=stamp_duty,
            total_fee=fee,
            net_cash_flow=net_cash_flow,
        ),
        event_time=event_time,
        created_at=event_time,
    )


def test_apply_buy_fill_event_updates_position_balance_and_fee_pnl() -> None:
    current_position = _position(
        qty=Decimal("250"),
        sellable_qty=Decimal("250"),
        avg_entry_price=Decimal("39.20"),
        mark_price=Decimal("39.50"),
        updated_at=BASE_TIME - timedelta(minutes=10),
    )
    current_balance = _balance_snapshot(
        total=Decimal("100000"),
        available=Decimal("100000"),
        locked=Decimal("0"),
    )
    fill_event = _fill_event(
        side=OrderSide.BUY,
        qty=Decimal("100"),
        price=Decimal("39.50"),
        fee=Decimal("1.2245"),
        commission=Decimal("1.1850"),
        transfer_fee=Decimal("0.0395"),
        stamp_duty=Decimal("0.0000"),
        net_cash_flow=Decimal("-3951.2245"),
        event_time=BASE_TIME,
    )

    update = apply_fill_event_to_portfolio(
        fill_event,
        current_position=current_position,
        current_balance=current_balance,
    )

    assert update.released_sellable_qty == Decimal("0")
    assert update.realized_pnl_delta == Decimal("-1.2245")
    assert update.position.qty == Decimal("350")
    assert update.position.sellable_qty == Decimal("250")
    assert update.position.avg_entry_price == Decimal("39.28571428571428571428571429")
    assert update.position.mark_price == Decimal("39.50")
    assert update.position.realized_pnl == Decimal("-1.2245")
    assert update.position.unrealized_pnl == Decimal("74.99999999999999999999999850")
    assert update.balance_snapshot.total == Decimal("96048.7755")
    assert update.balance_snapshot.available == Decimal("96048.7755")
    assert update.balance_snapshot.locked == Decimal("0")


def test_release_position_sellable_qty_unlocks_previous_trade_date_inventory() -> None:
    position = _position(
        qty=Decimal("300"),
        sellable_qty=Decimal("0"),
        avg_entry_price=Decimal("39.50"),
        mark_price=Decimal("39.50"),
        updated_at=BASE_TIME - timedelta(days=1),
    )
    release = release_position_sellable_qty(
        position,
        effective_trade_date=BASE_TIME.date(),
        released_at=BASE_TIME,
    )

    assert release.applied is True
    assert release.released_qty == Decimal("300")
    assert release.position.sellable_qty == Decimal("300")
    assert release.position.updated_at == BASE_TIME


def test_apply_sell_fill_event_releases_t_plus_one_qty_and_closes_odd_lot_position() -> None:
    current_position = _position(
        qty=Decimal("50"),
        sellable_qty=Decimal("0"),
        avg_entry_price=Decimal("39.50"),
        mark_price=Decimal("39.50"),
        realized_pnl=Decimal("-0.61225"),
        updated_at=BASE_TIME - timedelta(days=1),
    )
    current_balance = _balance_snapshot(
        total=Decimal("10000"),
        available=Decimal("10000"),
        locked=Decimal("0"),
    )
    fill_event = _fill_event(
        side=OrderSide.SELL,
        qty=Decimal("50"),
        price=Decimal("40.00"),
        fee=Decimal("1.6200"),
        commission=Decimal("0.6000"),
        transfer_fee=Decimal("0.0200"),
        stamp_duty=Decimal("1.0000"),
        net_cash_flow=Decimal("1998.3800"),
        event_time=BASE_TIME,
    )

    update = apply_fill_event_to_portfolio(
        fill_event,
        current_position=current_position,
        current_balance=current_balance,
    )

    assert update.released_sellable_qty == Decimal("50")
    assert update.realized_pnl_delta == Decimal("23.3800")
    assert update.position.status is PositionStatus.CLOSED
    assert update.position.qty == Decimal("0")
    assert update.position.sellable_qty == Decimal("0")
    assert update.position.avg_entry_price is None
    assert update.position.unrealized_pnl == Decimal("0")
    assert update.position.realized_pnl == Decimal("22.76775")
    assert update.balance_snapshot.total == Decimal("11998.3800")
    assert update.balance_snapshot.available == Decimal("11998.3800")
