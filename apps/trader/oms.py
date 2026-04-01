"""Persistence-first OMS application service for Phase 5A."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from src.config.settings import AshareSymbolRule
from src.domain.execution import (
    ExecutionReport,
    Fill,
    Order,
    OrderIntent,
    OrderIntentStatus,
    OrderType,
    SignalOrderIntentPlan,
    apply_order_update,
    build_order_id_for_intent,
    build_signal_order_intent_plan,
    create_order_from_intent,
    execution_report_is_empty,
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

    def save_fill(self, fill: Fill) -> Fill: ...

    def save_order(self, order: Order) -> Order: ...

    def save_order_intent(self, order_intent: OrderIntent) -> OrderIntent: ...

    def save_signal(self, signal: Signal) -> Signal: ...


class ExecutionGateway(Protocol):
    """Reserved async execution adapter point for Phase 5B."""

    async def submit_order(self, order: Order, order_intent: OrderIntent) -> ExecutionReport: ...

    async def cancel_order(self, order: Order) -> ExecutionReport: ...


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

    def save_fill(self, fill: Fill) -> Fill:
        return self.repositories.fills.save(fill)


class NoopExecutionGateway:
    """No-op adapter used until Phase 5B lands paper execution details."""

    async def submit_order(self, order: Order, order_intent: OrderIntent) -> ExecutionReport:
        return ExecutionReport()

    async def cancel_order(self, order: Order) -> ExecutionReport:
        return ExecutionReport()


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
                trader_run_id=persisted_signal.trader_run_id,
                account_id=persisted_signal.account_id,
                exchange=persisted_signal.exchange,
                symbol=persisted_signal.symbol,
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
            trader_run_id=persisted_signal.trader_run_id,
            account_id=persisted_signal.account_id,
            exchange=persisted_signal.exchange,
            symbol=persisted_signal.symbol,
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
            trader_run_id=persisted_signal.trader_run_id,
            account_id=persisted_signal.account_id,
            exchange=persisted_signal.exchange,
            symbol=persisted_signal.symbol,
            occurred_at=occurred_at,
            payload={
                "order_intent_id": persisted_intent.id,
                "order_status": persisted_order.status,
                "qty": persisted_order.qty,
                "decision_price": decision_price,
            },
        )

        try:
            execution_report = await self._execution_gateway.submit_order(
                persisted_order,
                persisted_intent,
            )
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
                trader_run_id=persisted_signal.trader_run_id,
                account_id=persisted_signal.account_id,
                exchange=persisted_signal.exchange,
                symbol=persisted_signal.symbol,
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
            trader_run_id=persisted_signal.trader_run_id,
            account_id=persisted_signal.account_id,
            exchange=persisted_signal.exchange,
            symbol=persisted_signal.symbol,
            occurred_at=occurred_at,
            payload={
                "order_intent_id": persisted_intent.id,
                "order_status": persisted_order.status,
                "decision_price": decision_price,
                "market_context": market_context,
                "execution_source": execution_report.source,
            },
        )

        latest_order = (
            persisted_order
            if execution_report_is_empty(execution_report)
            else self._apply_execution_report(
                report=execution_report,
                initial_order=persisted_order,
            )
        )

        return OmsSubmission(
            signal=persisted_signal,
            plan=plan,
            order_intent=persisted_submitted_intent,
            order=latest_order,
        )

    async def cancel_order(
        self,
        *,
        order_id: UUID,
        received_at: datetime | None = None,
    ) -> Order | None:
        """Cancel one active order through the execution gateway."""
        occurred_at = received_at or shanghai_now()
        order = self._persistence.get_order(order_id)
        if order is None:
            return None

        execution_report = await self._execution_gateway.cancel_order(order)
        if execution_report_is_empty(execution_report):
            return order

        self._persist_event(
            event_type="oms.execution_cancel_requested",
            related_object_type="order",
            related_object_id=order.id,
            trader_run_id=order.trader_run_id,
            account_id=order.account_id,
            exchange=order.exchange,
            symbol=order.symbol,
            occurred_at=occurred_at,
            payload={"execution_source": execution_report.source},
        )
        return self._apply_execution_report(
            report=execution_report,
            initial_order=order,
        )

    def _apply_execution_report(
        self,
        *,
        report: ExecutionReport,
        initial_order: Order,
    ) -> Order:
        current_order = initial_order
        for order_update in report.order_updates:
            current_order = self._persistence.save_order(
                apply_order_update(current_order, order_update)
            )
            self._persist_event(
                event_type="execution.order_updated",
                related_object_type="order",
                related_object_id=current_order.id,
                source=report.source,
                trader_run_id=current_order.trader_run_id,
                account_id=current_order.account_id,
                exchange=current_order.exchange,
                symbol=current_order.symbol,
                occurred_at=order_update.event_time,
                payload={
                    "execution_source": report.source,
                    "order_update": order_update,
                },
            )

        for fill_event in report.fill_events:
            persisted_fill = self._persistence.save_fill(fill_event.fill)
            self._persist_event(
                event_type="execution.fill_recorded",
                related_object_type="fill",
                related_object_id=persisted_fill.id,
                source=report.source,
                trader_run_id=fill_event.trader_run_id,
                account_id=fill_event.account_id,
                exchange=fill_event.exchange,
                symbol=fill_event.symbol,
                occurred_at=fill_event.event_time,
                payload={
                    "execution_source": report.source,
                    "fill_event": fill_event,
                },
            )

        return current_order

    def _persist_event(
        self,
        *,
        event_type: str,
        related_object_type: str,
        related_object_id: UUID,
        trader_run_id: UUID,
        account_id: str,
        exchange: str,
        symbol: str,
        occurred_at: datetime,
        payload: dict[str, object],
        source: str = "trader_oms",
    ) -> None:
        self._persistence.save_event_log(
            EventLogEntry(
                event_type=event_type,
                source=source,
                trader_run_id=trader_run_id,
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
                related_object_type=related_object_type,
                related_object_id=related_object_id,
                event_time=occurred_at,
                ingest_time=occurred_at,
                created_at=occurred_at,
                payload_json=payload,
            )
        )
