"""Minimal control-plane service used by the Phase 6B API."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from src.config import Settings
from src.domain.execution import OrderStatus
from src.infra.db import SqlAlchemyRepositories, session_scope
from src.infra.db.models import OrderIntentRecord, OrderRecord
from src.infra.observability import SignalArkObservability, build_observability
from src.shared.types import shanghai_now

from apps.trader.control_plane import TraderControlPlaneStore
from apps.trader.oms import build_default_trader_oms_service


class ApiControlPlaneService:
    """Coordinate DB-backed status queries and operator actions."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker,
        control_store: TraderControlPlaneStore,
        observability: SignalArkObservability | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._control_store = control_store
        self._observability = observability or build_observability(
            settings=settings,
            service="api",
            logger_name="signalark.api.control_plane",
        )
        self._control_store.ensure_schema()

    def live_payload(self) -> dict[str, object]:
        database_connected = False
        try:
            database_connected = self._control_store.ping()
        except Exception:
            database_connected = False
        return {
            "status": "alive",
            "service": self._settings.app_name,
            "database_connected": database_connected,
        }

    def ready_payload(self) -> dict[str, object]:
        try:
            return self._control_store.build_status_view(
                account_id=self._settings.account_id,
                timeframe=self._settings.primary_timeframe,
                market_stale_threshold_seconds=self._settings.market_stale_threshold_seconds,
            )
        except Exception as exc:
            return {
                "status": "not_ready",
                "ready": False,
                "account_id": self._settings.account_id,
                "message": str(exc),
            }

    def status_payload(self) -> dict[str, object]:
        payload = self.ready_payload()
        payload.update(
            {
                "service": self._settings.app_name,
                "env": self._settings.env,
                "execution_mode": self._settings.execution_mode,
                "exchange": self._settings.exchange,
                "symbols": self._settings.symbols,
            }
        )
        return payload

    def positions_payload(self) -> dict[str, object]:
        with session_scope(self._session_factory) as session:
            repositories = SqlAlchemyRepositories.from_session(session)
            positions = repositories.recovery.load_runtime_state(
                account_id=self._settings.account_id,
                event_limit=0,
            ).open_positions
        return {
            "account_id": self._settings.account_id,
            "positions": [position.model_dump(mode="json") for position in positions],
        }

    def active_orders_payload(self) -> dict[str, object]:
        with session_scope(self._session_factory) as session:
            query = (
                select(OrderRecord, OrderIntentRecord.reduce_only)
                .join(OrderIntentRecord, OrderIntentRecord.id == OrderRecord.order_intent_id)
                .where(OrderRecord.account_id == self._settings.account_id)
                .where(
                    OrderRecord.status.in_(
                        (
                            OrderStatus.NEW.value,
                            OrderStatus.ACK.value,
                            OrderStatus.PARTIALLY_FILLED.value,
                        )
                    )
                )
                .order_by(OrderRecord.updated_at.asc(), OrderRecord.id.asc())
            )
            rows = session.execute(query).all()
        return {
            "account_id": self._settings.account_id,
            "orders": [
                {
                    "order_id": order_record.id,
                    "order_intent_id": order_record.order_intent_id,
                    "symbol": order_record.symbol,
                    "side": order_record.side,
                    "order_type": order_record.order_type,
                    "qty": order_record.qty,
                    "filled_qty": order_record.filled_qty,
                    "status": order_record.status,
                    "reduce_only": reduce_only,
                    "submitted_at": order_record.submitted_at.isoformat(),
                    "updated_at": order_record.updated_at.isoformat(),
                }
                for order_record, reduce_only in rows
            ],
        }

    async def pause_strategy(self) -> dict[str, object]:
        snapshot = self._control_store.set_strategy_enabled(
            account_id=self._settings.account_id,
            enabled=False,
        )
        return self._control_action_response(
            accepted=True,
            message="Strategy paused.",
            control_state=snapshot.control_state.value,
            event_name="control.strategy_paused",
            reason_code="OPERATOR_REQUEST",
        )

    async def resume_strategy(self) -> dict[str, object]:
        snapshot = self._control_store.set_strategy_enabled(
            account_id=self._settings.account_id,
            enabled=True,
        )
        return self._control_action_response(
            accepted=True,
            message="Strategy resumed.",
            control_state=snapshot.control_state.value,
            event_name="control.strategy_resumed",
            reason_code="OPERATOR_REQUEST",
        )

    async def enable_kill_switch(self) -> dict[str, object]:
        snapshot = self._control_store.set_kill_switch(
            account_id=self._settings.account_id,
            active=True,
        )
        return self._control_action_response(
            accepted=True,
            message="Kill switch enabled; only reducing or flattening actions remain allowed.",
            control_state=snapshot.control_state.value,
            event_name="control.kill_switch_enabled",
            severity="warning",
            notify=True,
            reason_code="OPERATOR_REQUEST",
        )

    async def disable_kill_switch(self) -> dict[str, object]:
        snapshot = self._control_store.set_kill_switch(
            account_id=self._settings.account_id,
            active=False,
        )
        return self._control_action_response(
            accepted=True,
            message="Kill switch disabled; protection mode, if active, is unchanged.",
            control_state=snapshot.control_state.value,
            event_name="control.kill_switch_disabled",
            notify=True,
            reason_code="OPERATOR_REQUEST",
        )

    async def cancel_all(self) -> dict[str, object]:
        snapshot = self._control_store.mark_cancel_all_requested(
            account_id=self._settings.account_id,
        )
        oms_service = build_default_trader_oms_service(
            settings=self._settings,
            session_factory=self._session_factory,
            control_store=self._control_store,
            observability=self._observability,
        )
        try:
            result = await oms_service.cancel_all_orders(
                account_id=self._settings.account_id,
                control_state=snapshot.control_state,
            )
        except Exception as exc:
            self._observability.emit(
                event_name="control.cancel_all_failed",
                severity="critical",
                message="Cancel-all failed before all eligible orders could be cancelled.",
                notify=True,
                bypass_cooldown=True,
                account_id=self._settings.account_id,
                control_state=snapshot.control_state.value,
                reason_code="CANCEL_ALL_FAILED",
                details={"error": str(exc)},
            )
            raise
        response = self._control_action_response(
            accepted=True,
            message="Cancel-all request applied to active orders.",
            control_state=snapshot.control_state.value,
            event_name="control.cancel_all_requested",
            severity="warning",
            notify=True,
            reason_code="OPERATOR_REQUEST",
            details={
                "requested_order_count": result.requested_order_count,
                "cancelled_order_count": result.cancelled_order_count,
                "skipped_order_count": result.skipped_order_count,
            },
        )
        response.update(
            {
                "requested_order_count": result.requested_order_count,
                "cancelled_order_count": result.cancelled_order_count,
                "skipped_order_count": result.skipped_order_count,
            }
        )
        return response

    def _control_action_response(
        self,
        *,
        accepted: bool,
        message: str,
        control_state: str,
        event_name: str | None = None,
        severity: str = "info",
        notify: bool = False,
        reason_code: str | None = None,
        details: dict[str, object] | None = None,
    ) -> dict[str, object]:
        status_payload = self._control_store.build_status_view(
            account_id=self._settings.account_id,
            timeframe=self._settings.primary_timeframe,
            market_stale_threshold_seconds=self._settings.market_stale_threshold_seconds,
        )
        response = {
            "accepted": accepted,
            "control_state": control_state,
            "trader_run_id": status_payload.get("trader_run_id"),
            "instance_id": status_payload.get("instance_id"),
            "effective_at": shanghai_now().isoformat(),
            "message": message,
        }
        if event_name is not None:
            self._observability.emit(
                event_name=event_name,
                severity=severity,
                message=message,
                notify=notify,
                trader_run_id=status_payload.get("trader_run_id"),
                instance_id=status_payload.get("instance_id"),
                account_id=self._settings.account_id,
                exchange=self._settings.exchange,
                control_state=control_state,
                reason_code=reason_code,
                details=details,
            )
        return response
