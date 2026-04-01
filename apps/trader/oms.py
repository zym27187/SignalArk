"""Persistence-first OMS application service for Phase 5A."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from src.config.settings import AshareSymbolRule
from src.domain.execution import (
    Order,
    OrderIntent,
    OrderIntentStatus,
    OrderType,
    SignalOrderIntentPlan,
    build_order_id_for_intent,
    build_signal_order_intent_plan,
    create_order_from_intent,
)
from src.domain.market import MarketStateSnapshot
from src.domain.portfolio import Position
from src.domain.strategy import Signal
from src.infra.db import EventLogEntry, SqlAlchemyRepositories
from src.shared.types import shanghai_now


class OmsPersistencePort(Protocol):
    """Minimal persistence contract used by the trader OMS skeleton."""

    def get_position(self, *, account_id: str, exchange: str, symbol: str) -> Position | None: ...

    def get_order(self, order_id: UUID) -> Order | None: ...

    def save_event_log(self, event_log: EventLogEntry) -> EventLogEntry: ...

    def save_order(self, order: Order) -> Order: ...

    def save_order_intent(self, order_intent: OrderIntent) -> OrderIntent: ...

    def save_signal(self, signal: Signal) -> Signal: ...


class ExecutionGateway(Protocol):
    """Reserved async execution adapter point for Phase 5B."""

    async def submit_order(self, order: Order, order_intent: OrderIntent) -> None: ...


@dataclass(slots=True)
class RepositoryBackedOmsPersistence:
    """Bridge the trader OMS service onto the SQLAlchemy repository bundle."""

    repositories: SqlAlchemyRepositories

    def save_signal(self, signal: Signal) -> Signal:
        return self.repositories.signals.save(signal)

    def get_position(self, *, account_id: str, exchange: str, symbol: str) -> Position | None:
        return self.repositories.positions.get_by_symbol(
            account_id=account_id,
            exchange=exchange,
            symbol=symbol,
        )

    def save_order_intent(self, order_intent: OrderIntent) -> OrderIntent:
        return self.repositories.order_intents.save(order_intent)

    def save_order(self, order: Order) -> Order:
        return self.repositories.orders.save(order)

    def get_order(self, order_id: UUID) -> Order | None:
        return self.repositories.orders.get(order_id)

    def save_event_log(self, event_log: EventLogEntry) -> EventLogEntry:
        return self.repositories.event_logs.save(event_log)


class NoopExecutionGateway:
    """No-op adapter used until Phase 5B lands paper execution details."""

    async def submit_order(self, order: Order, order_intent: OrderIntent) -> None:
        return None


@dataclass(frozen=True, slots=True)
class OmsSubmission:
    """The persisted OMS objects produced by one signal-handling attempt."""

    signal: Signal
    plan: SignalOrderIntentPlan
    order_intent: OrderIntent
    order: Order


class TraderOmsService:
    """Persist order intents before invoking any execution adapter."""

    def __init__(
        self,
        persistence: OmsPersistencePort,
        *,
        execution_gateway: ExecutionGateway | None = None,
    ) -> None:
        self._persistence = persistence
        self._execution_gateway = execution_gateway or NoopExecutionGateway()

    async def submit_signal(
        self,
        *,
        signal: Signal,
        symbol_rule: AshareSymbolRule,
        decision_price: Decimal,
        market_context: MarketStateSnapshot,
        current_position: Position | None = None,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal | None = None,
        received_at: datetime | None = None,
    ) -> OmsSubmission | None:
        """Persist Signal -> OrderIntent -> Order before execution handoff."""
        occurred_at = received_at or shanghai_now()
        persisted_signal = self._persistence.save_signal(signal)
        resolved_position = current_position or self._persistence.get_position(
            account_id=signal.account_id,
            exchange=signal.exchange,
            symbol=signal.symbol,
        )
        plan = build_signal_order_intent_plan(
            signal=persisted_signal,
            symbol_rule=symbol_rule,
            current_position=resolved_position,
            decision_price=decision_price,
            market_context=market_context,
            order_type=order_type,
            price=price,
        )

        if not plan.actionable:
            self._persist_event(
                event_type="oms.signal_skipped",
                related_object_type="signal",
                related_object_id=persisted_signal.id,
                signal=persisted_signal,
                occurred_at=occurred_at,
                payload={
                    "skip_reason": plan.skip_reason,
                    "target_position": persisted_signal.target_position,
                    "current_position_qty": plan.current_position_qty,
                    "current_sellable_qty": plan.current_sellable_qty,
                    "decision_price": decision_price,
                    "market_context": market_context,
                },
            )
            return None

        order_intent = plan.to_order_intent(created_at=occurred_at)
        persisted_intent = self._persistence.save_order_intent(order_intent)

        order_id = build_order_id_for_intent(persisted_intent.id)
        if persisted_intent.status is OrderIntentStatus.SUBMITTED:
            existing_order = self._persistence.get_order(order_id)
            if existing_order is None:
                existing_order = self._persistence.save_order(
                    create_order_from_intent(
                        persisted_intent,
                        order_id=order_id,
                        submitted_at=occurred_at,
                    )
                )
            return OmsSubmission(
                signal=persisted_signal,
                plan=plan,
                order_intent=persisted_intent,
                order=existing_order,
            )

        self._persist_event(
            event_type="oms.order_intent_persisted",
            related_object_type="order_intent",
            related_object_id=persisted_intent.id,
            signal=persisted_signal,
            occurred_at=occurred_at,
            payload={
                "signal_id": persisted_signal.id,
                "target_position": persisted_signal.target_position,
                "current_position_qty": plan.current_position_qty,
                "current_sellable_qty": plan.current_sellable_qty,
                "raw_delta_qty": plan.raw_delta_qty,
                "order_intent_qty": plan.qty,
                "decision_price": decision_price,
                "market_context": market_context,
                "reduce_only": plan.reduce_only,
                "odd_lot_sell": plan.odd_lot_sell,
            },
        )

        order = create_order_from_intent(
            persisted_intent,
            order_id=order_id,
            submitted_at=occurred_at,
        )
        persisted_order = self._persistence.save_order(order)

        self._persist_event(
            event_type="oms.order_persisted",
            related_object_type="order",
            related_object_id=persisted_order.id,
            signal=persisted_signal,
            occurred_at=occurred_at,
            payload={
                "order_intent_id": persisted_intent.id,
                "order_status": persisted_order.status,
                "qty": persisted_order.qty,
                "decision_price": decision_price,
            },
        )

        try:
            await self._execution_gateway.submit_order(persisted_order, persisted_intent)
        except Exception as exc:
            errored_order = persisted_order.model_copy(
                update={
                    "last_error_code": "SUBMIT_FAILED",
                    "last_error_message": str(exc),
                    "updated_at": occurred_at,
                }
            )
            self._persistence.save_order(errored_order)
            self._persist_event(
                event_type="oms.execution_submission_failed",
                related_object_type="order",
                related_object_id=persisted_order.id,
                signal=persisted_signal,
                occurred_at=occurred_at,
                payload={"order_intent_id": persisted_intent.id, "error": str(exc)},
            )
            raise

        submitted_intent = persisted_intent.model_copy(
            update={"status": OrderIntentStatus.SUBMITTED}
        )
        persisted_submitted_intent = self._persistence.save_order_intent(submitted_intent)

        self._persist_event(
            event_type="oms.execution_submission_requested",
            related_object_type="order",
            related_object_id=persisted_order.id,
            signal=persisted_signal,
            occurred_at=occurred_at,
            payload={
                "order_intent_id": persisted_intent.id,
                "order_status": persisted_order.status,
                "decision_price": decision_price,
                "market_context": market_context,
            },
        )

        return OmsSubmission(
            signal=persisted_signal,
            plan=plan,
            order_intent=persisted_submitted_intent,
            order=persisted_order,
        )

    def _persist_event(
        self,
        *,
        event_type: str,
        related_object_type: str,
        related_object_id: UUID,
        signal: Signal,
        occurred_at: datetime,
        payload: dict[str, object],
    ) -> None:
        self._persistence.save_event_log(
            EventLogEntry(
                event_type=event_type,
                source="trader_oms",
                trader_run_id=signal.trader_run_id,
                account_id=signal.account_id,
                exchange=signal.exchange,
                symbol=signal.symbol,
                related_object_type=related_object_type,
                related_object_id=related_object_id,
                event_time=occurred_at,
                ingest_time=occurred_at,
                created_at=occurred_at,
                payload_json=payload,
            )
        )
