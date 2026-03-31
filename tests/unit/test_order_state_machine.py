from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError
from src.domain.execution import (
    Order,
    OrderSide,
    OrderStateTransitionError,
    OrderStatus,
    OrderType,
    can_transition_order_status,
    validate_order_status_transition,
)

BASE_TIME = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
TRADER_RUN_ID = UUID("44444444-4444-4444-8444-444444444444")
ORDER_INTENT_ID = UUID("55555555-5555-4555-8555-555555555555")


def build_order(**updates: object) -> Order:
    payload: dict[str, object] = {
        "order_intent_id": ORDER_INTENT_ID,
        "trader_run_id": TRADER_RUN_ID,
        "account_id": "paper_account_001",
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "side": OrderSide.BUY,
        "order_type": OrderType.MARKET,
        "qty": Decimal("1.0"),
        "status": OrderStatus.NEW,
        "submitted_at": BASE_TIME,
        "updated_at": BASE_TIME,
    }
    payload.update(updates)
    return Order(**payload)


@pytest.mark.parametrize(
    ("current", "new"),
    [
        (OrderStatus.NEW, OrderStatus.ACK),
        (OrderStatus.NEW, OrderStatus.CANCELED),
        (OrderStatus.ACK, OrderStatus.PARTIALLY_FILLED),
        (OrderStatus.ACK, OrderStatus.FILLED),
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.PARTIALLY_FILLED),
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELED),
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED),
        (OrderStatus.FILLED, OrderStatus.FILLED),
    ],
)
def test_order_status_transition_matrix_allows_valid_paths(
    current: OrderStatus, new: OrderStatus
) -> None:
    assert can_transition_order_status(current, new) is True
    validate_order_status_transition(current, new)


@pytest.mark.parametrize(
    ("current", "new"),
    [
        (OrderStatus.NEW, OrderStatus.FILLED),
        (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED),
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.REJECTED),
        (OrderStatus.CANCELED, OrderStatus.ACK),
        (OrderStatus.REJECTED, OrderStatus.ACK),
        (OrderStatus.FILLED, OrderStatus.CANCELED),
    ],
)
def test_order_status_transition_matrix_rejects_invalid_paths(
    current: OrderStatus, new: OrderStatus
) -> None:
    assert can_transition_order_status(current, new) is False
    with pytest.raises(OrderStateTransitionError, match="Invalid order status transition"):
        validate_order_status_transition(current, new)


def test_order_transition_to_validates_partial_and_fill_invariants() -> None:
    order = build_order()
    acked = order.transition_to(OrderStatus.ACK, updated_at=BASE_TIME + timedelta(seconds=1))
    partial = acked.transition_to(
        OrderStatus.PARTIALLY_FILLED,
        filled_qty=Decimal("0.4"),
        avg_fill_price=Decimal("100"),
        updated_at=BASE_TIME + timedelta(seconds=2),
    )
    filled = partial.transition_to(
        OrderStatus.FILLED,
        filled_qty=Decimal("1.0"),
        avg_fill_price=Decimal("101"),
        updated_at=BASE_TIME + timedelta(seconds=3),
    )

    assert acked.status is OrderStatus.ACK
    assert partial.status is OrderStatus.PARTIALLY_FILLED
    assert partial.remaining_qty == Decimal("0.6")
    assert filled.status is OrderStatus.FILLED
    assert filled.remaining_qty == Decimal("0.0")


def test_order_transition_to_rejects_missing_partial_fill_data() -> None:
    order = build_order(status=OrderStatus.ACK, updated_at=BASE_TIME + timedelta(seconds=1))

    with pytest.raises(ValidationError, match="PARTIALLY_FILLED orders require avg_fill_price"):
        order.transition_to(
            OrderStatus.PARTIALLY_FILLED,
            filled_qty=Decimal("0.4"),
            updated_at=BASE_TIME + timedelta(seconds=2),
        )
