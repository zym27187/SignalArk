"""Trader runtime service, in-process event bus, and lifecycle wiring."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

import structlog
from src.config import Settings
from src.config.settings import AshareSymbolRule
from src.domain.events import BarEvent
from src.domain.strategy import Signal, build_strategy
from src.infra.db import create_database_engine, create_session_factory
from src.infra.messaging import InProcessEventBus
from src.infra.observability import build_observability
from src.shared.logging import bind_log_context

from apps.collector.service import CollectorService, build_default_collector_service
from apps.trader.control_plane import TraderControlPlaneStore, TraderControlRuntime
from apps.trader.oms import TraderOmsService, build_default_trader_oms_service
from apps.trader.reconciliation import (
    SessionFactoryBackedReconciliationStore,
    TraderReconciliationRuntime,
)
from apps.trader.runtime import TraderRuntimeState


class TraderEventSource(Protocol):
    """Minimal upstream contract for events entering the trader loop."""

    async def aclose(self) -> None: ...

    def events(self) -> AsyncIterator[object]: ...


class StrategyPort(Protocol):
    """Future strategy runtime hook fed by actionable bars."""

    async def on_bar(self, event: BarEvent, context: TraderEventContext) -> object | None: ...


class RiskPort(Protocol):
    """Future risk runtime hook reserved for Phase 5 signal handling."""

    async def on_signal(
        self,
        signal: object,
        event: BarEvent,
        context: TraderEventContext,
    ) -> object | None: ...


class OmsPort(Protocol):
    """Future OMS runtime hook reserved for Phase 5 order-intent handling."""

    async def on_order_intent(
        self,
        order_intent: object,
        context: TraderEventContext,
    ) -> None: ...


@dataclass(slots=True, frozen=True)
class TraderEventContext:
    """Process context shared with downstream strategy/risk/OMS handlers."""

    trader_run_id: str
    instance_id: str
    received_at: datetime
    runtime_state: TraderRuntimeState

    @property
    def trader_run_uuid(self) -> UUID:
        return UUID(self.trader_run_id)


@dataclass(slots=True)
class TraderPipelinePorts:
    """Reserved downstream integration points for the trading pipeline."""

    strategy: StrategyPort | None = None
    risk: RiskPort | None = None
    oms: OmsPort | None = None


class CollectorBarEventSource:
    """Adapter that turns the collector service into a trader event source."""

    def __init__(self, collector: CollectorService) -> None:
        self._collector = collector

    def events(self) -> AsyncIterator[object]:
        return self._collector.collect_actionable_bars()

    async def aclose(self) -> None:
        await self._collector.aclose()


class BarTriggerGate:
    """Ignore non-final bars and duplicate final bars at the strategy boundary."""

    def __init__(self, *, recent_capacity: int = 4096) -> None:
        if recent_capacity < 1:
            raise ValueError("recent_capacity must be at least 1")

        self._recent_capacity = recent_capacity
        self._recent_bar_keys: deque[str] = deque()
        self._recent_lookup: set[str] = set()

    def allow(self, event: BarEvent) -> tuple[bool, str]:
        if not event.actionable:
            return False, "bar_is_not_closed_and_final"

        if event.bar_key in self._recent_lookup:
            return False, "bar_key_already_triggered"

        self._recent_lookup.add(event.bar_key)
        self._recent_bar_keys.append(event.bar_key)

        while len(self._recent_bar_keys) > self._recent_capacity:
            expired_key = self._recent_bar_keys.popleft()
            self._recent_lookup.discard(expired_key)

        return True, "new_final_bar"


@dataclass(slots=True)
class OmsSignalRiskRouter:
    """Route strategy-generated signals into the settings-backed OMS service."""

    oms_service: TraderOmsService
    symbol_rules: Mapping[str, AshareSymbolRule]
    control_runtime: TraderControlRuntime | None = None
    _symbol_rules: dict[str, AshareSymbolRule] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._symbol_rules = {
            str(symbol).strip().upper(): rule for symbol, rule in self.symbol_rules.items()
        }

    @property
    def oms_handler_name(self) -> str:
        return type(self.oms_service).__name__

    async def on_signal(
        self,
        signal: object,
        event: BarEvent,
        context: TraderEventContext,
    ) -> object | None:
        if not isinstance(signal, Signal):
            return None

        control_state = context.runtime_state.control_state
        submission_guard = None
        if self.control_runtime is not None:
            control_state = self.control_runtime.control_state
            submission_guard = self.control_runtime.submission_guard()

        return await self.oms_service.submit_signal(
            signal=signal,
            symbol_rule=self._symbol_rules.get(signal.symbol),
            decision_price=event.decision_price,
            market_context=event.market_state,
            strategy_input_snapshot=context.runtime_state.last_strategy_input_snapshot,
            strategy_signal_snapshot=context.runtime_state.last_strategy_signal_snapshot,
            strategy_reason_summary=context.runtime_state.last_strategy_reason_summary,
            control_state=control_state,
            submission_guard=submission_guard,
            received_at=context.received_at,
        )


class TraderService:
    """Own the trader lifecycle, source loop, event bus, and runtime state."""

    def __init__(
        self,
        source: TraderEventSource,
        *,
        event_bus: InProcessEventBus | None = None,
        runtime_state: TraderRuntimeState | None = None,
        pipeline: TraderPipelinePorts | None = None,
        control_runtime: TraderControlRuntime | None = None,
        reconciliation_runtime: TraderReconciliationRuntime | None = None,
        bind_run_id_to_logs: bool = True,
        bar_trigger_capacity: int = 4096,
    ) -> None:
        self._source = source
        self._event_bus = event_bus or InProcessEventBus()
        self._runtime_state = runtime_state or TraderRuntimeState()
        self._pipeline = pipeline or TraderPipelinePorts()
        self._control_runtime = control_runtime
        self._reconciliation_runtime = reconciliation_runtime
        self._bind_run_id_to_logs = bind_run_id_to_logs
        self._bar_trigger_gate = BarTriggerGate(recent_capacity=bar_trigger_capacity)
        self._logger = structlog.get_logger(__name__)
        self._source_task: asyncio.Task[None] | None = None
        self._stop_requested = asyncio.Event()
        self._lifecycle_lock = asyncio.Lock()
        self._closed = False

        self._bind_pipeline_state()
        self._event_bus.subscribe(BarEvent, self._handle_bar_event, name="trader.bar_router")

    @property
    def runtime_state(self) -> TraderRuntimeState:
        return self._runtime_state

    @property
    def event_bus(self) -> InProcessEventBus:
        return self._event_bus

    async def start(self) -> None:
        """Start the event bus and the upstream source-consumer loop."""
        async with self._lifecycle_lock:
            if self._source_task is not None:
                raise RuntimeError("trader service has already been started")

            if self._bind_run_id_to_logs:
                bind_log_context(
                    trader_run_id=self._runtime_state.trader_run_id,
                    trader_instance_id=self._runtime_state.instance_id,
                )

            self._runtime_state.mark_starting()
            await self._event_bus.start()
            self._source_task = asyncio.create_task(
                self._consume_events(),
                name="trader-source-loop",
            )
            self._runtime_state.mark_running(ready=self._control_runtime is None)
            control_runtime_started = False
            reconciliation_runtime_started = False
            try:
                if self._control_runtime is not None:
                    await self._control_runtime.start(self._runtime_state)
                    control_runtime_started = True
                if self._reconciliation_runtime is not None:
                    await self._reconciliation_runtime.start(self._runtime_state)
                    reconciliation_runtime_started = True
            except Exception:
                if self._source_task is not None and not self._source_task.done():
                    self._source_task.cancel()
                    await asyncio.gather(self._source_task, return_exceptions=True)
                if reconciliation_runtime_started and self._reconciliation_runtime is not None:
                    await self._reconciliation_runtime.stop()
                if control_runtime_started and self._control_runtime is not None:
                    await self._control_runtime.stop(reason="runtime_dependency_start_failed")
                await self._event_bus.stop()
                await self._source.aclose()
                self._runtime_state.mark_stopped("runtime_dependency_start_failed")
                self._closed = True
                raise

            self._logger.info(
                "trader_started",
                trader_run_id=self._runtime_state.trader_run_id,
                instance_id=self._runtime_state.instance_id,
                subscriptions=self._event_bus.subscription_count,
                pipeline=self._runtime_state.pipeline.snapshot(),
            )

    async def run(self) -> None:
        """Run the trader until its source ends or the task is cancelled."""
        await self.start()

        stop_wait_task = asyncio.create_task(
            self._stop_requested.wait(),
            name="trader-stop-wait",
        )
        dispatcher_wait_task = asyncio.create_task(
            self._event_bus.wait_until_stopped(),
            name="trader-dispatcher-wait",
        )

        try:
            done, pending = await asyncio.wait(
                {self._source_task, stop_wait_task, dispatcher_wait_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if self._source_task in done:
                source_exc = self._source_task.exception()
                if source_exc is not None:
                    await self.stop(reason="source_failed")
                    raise source_exc

                await self.stop(reason="source_exhausted")
                return

            if dispatcher_wait_task in done and not self._stop_requested.is_set():
                dispatcher_exc = dispatcher_wait_task.exception()
                reason = "dispatcher_failed" if dispatcher_exc else "dispatcher_stopped"
                await self.stop(reason=reason)
                if dispatcher_exc is not None:
                    raise dispatcher_exc
                return

            await asyncio.gather(*pending)
        except asyncio.CancelledError:
            await self.stop(reason="cancelled")
            raise
        finally:
            stop_wait_task.cancel()
            dispatcher_wait_task.cancel()
            await asyncio.gather(stop_wait_task, dispatcher_wait_task, return_exceptions=True)

    async def stop(self, *, reason: str = "requested") -> None:
        """Stop the source loop and drain the event bus exactly once."""
        async with self._lifecycle_lock:
            if self._closed:
                return

            self._stop_requested.set()
            if self._runtime_state.status not in {"stopping", "stopped"}:
                self._runtime_state.mark_stopping(reason)
                self._logger.info(
                    "trader_stopping",
                    trader_run_id=self._runtime_state.trader_run_id,
                    instance_id=self._runtime_state.instance_id,
                    reason=reason,
                )

            if self._source_task is not None and not self._source_task.done():
                self._source_task.cancel()
                await asyncio.gather(self._source_task, return_exceptions=True)

            cleanup_errors: list[Exception] = []
            try:
                await self._event_bus.stop()
            except Exception as exc:  # pragma: no cover - defensive cleanup path
                cleanup_errors.append(exc)

            try:
                await self._source.aclose()
            except Exception as exc:  # pragma: no cover - defensive cleanup path
                cleanup_errors.append(exc)

            self._runtime_state.mark_stopped(reason)
            if self._reconciliation_runtime is not None:
                await self._reconciliation_runtime.stop()
            if self._control_runtime is not None:
                await self._control_runtime.stop(reason=reason)
            self._closed = True
            self._logger.info(
                "trader_stopped",
                trader_run_id=self._runtime_state.trader_run_id,
                instance_id=self._runtime_state.instance_id,
                reason=reason,
                runtime_state=self.runtime_snapshot(),
            )

            if cleanup_errors:
                raise cleanup_errors[0]

    async def aclose(self) -> None:
        """Compatibility alias for callers that manage resources generically."""
        await self.stop()

    def health_payload(self) -> dict[str, object]:
        """Return the health view reserved for future API endpoints."""
        return self._runtime_state.health_payload(
            event_bus_pending_count=self._event_bus.pending_count,
        )

    def readiness_payload(self) -> dict[str, object]:
        """Return the readiness and lease-integration view for the control plane."""
        return self._runtime_state.readiness_payload(
            event_bus_pending_count=self._event_bus.pending_count,
        )

    def runtime_snapshot(self) -> dict[str, object]:
        """Return the full runtime snapshot for diagnostics and future endpoints."""
        return self._runtime_state.snapshot(
            event_bus_pending_count=self._event_bus.pending_count,
        )

    async def _consume_events(self) -> None:
        async for event in self._source.events():
            if self._stop_requested.is_set():
                return

            await self._event_bus.publish(event)
            self._logger.info(
                "trader_event_received",
                trader_run_id=self._runtime_state.trader_run_id,
                instance_id=self._runtime_state.instance_id,
                event_type=type(event).__name__,
                bar_key=getattr(event, "bar_key", None),
            )

    async def _handle_bar_event(self, event: object) -> None:
        if not isinstance(event, BarEvent):
            return

        self._runtime_state.record_event(event)
        if self._control_runtime is not None:
            await self._control_runtime.observe_bar(event)

        if self._runtime_state.readiness_status != "ready":
            self._runtime_state.record_ignored_bar(event, "trader_not_ready")
            self._logger.info(
                "trader_bar_ignored",
                trader_run_id=self._runtime_state.trader_run_id,
                instance_id=self._runtime_state.instance_id,
                bar_key=event.bar_key,
                exchange=event.exchange,
                symbol=event.symbol,
                timeframe=event.timeframe,
                reason="trader_not_ready",
                final=event.final,
                closed=event.closed,
            )
            return

        if not self._runtime_state.strategy_enabled:
            self._runtime_state.record_ignored_bar(event, "strategy_paused")
            self._logger.info(
                "trader_bar_ignored",
                trader_run_id=self._runtime_state.trader_run_id,
                instance_id=self._runtime_state.instance_id,
                bar_key=event.bar_key,
                exchange=event.exchange,
                symbol=event.symbol,
                timeframe=event.timeframe,
                reason="strategy_paused",
                final=event.final,
                closed=event.closed,
            )
            return

        allowed, reason = self._bar_trigger_gate.allow(event)
        if not allowed:
            self._runtime_state.record_ignored_bar(event, reason)
            self._logger.info(
                "trader_bar_ignored",
                trader_run_id=self._runtime_state.trader_run_id,
                instance_id=self._runtime_state.instance_id,
                bar_key=event.bar_key,
                exchange=event.exchange,
                symbol=event.symbol,
                timeframe=event.timeframe,
                reason=reason,
                final=event.final,
                closed=event.closed,
            )
            return

        self._runtime_state.record_strategy_bar(event)
        if self._control_runtime is not None:
            await self._control_runtime.persist_runtime_audit()
        context = TraderEventContext(
            trader_run_id=self._runtime_state.trader_run_id,
            instance_id=self._runtime_state.instance_id,
            received_at=event.ingest_time,
            runtime_state=self._runtime_state,
        )
        self._logger.info(
            "trader_bar_ready_for_strategy",
            trader_run_id=context.trader_run_id,
            instance_id=context.instance_id,
            bar_key=event.bar_key,
            exchange=event.exchange,
            symbol=event.symbol,
            timeframe=event.timeframe,
            source_kind=event.source_kind,
        )

        if self._pipeline.strategy is not None:
            signal = await self._pipeline.strategy.on_bar(event, context)
            self._record_strategy_decision(
                strategy=self._pipeline.strategy,
                event=event,
                signal=signal,
            )
            if signal is not None and self._pipeline.risk is not None:
                await self._pipeline.risk.on_signal(signal, event, context)

    def _bind_pipeline_state(self) -> None:
        if self._pipeline.strategy is not None:
            self._runtime_state.pipeline.strategy.bind(type(self._pipeline.strategy).__name__)
        if self._pipeline.risk is not None:
            self._runtime_state.pipeline.risk.bind(type(self._pipeline.risk).__name__)
            oms_handler_name = getattr(self._pipeline.risk, "oms_handler_name", None)
            if isinstance(oms_handler_name, str) and oms_handler_name:
                self._runtime_state.pipeline.oms.bind(oms_handler_name)
        if self._pipeline.oms is not None:
            self._runtime_state.pipeline.oms.bind(type(self._pipeline.oms).__name__)

    def _record_strategy_decision(
        self,
        *,
        strategy: StrategyPort,
        event: BarEvent,
        signal: object | None,
    ) -> None:
        if not isinstance(signal, Signal):
            return

        input_snapshot = _default_strategy_input_snapshot(event)
        signal_snapshot = _default_signal_snapshot(signal)
        reason_summary = signal.reason_summary

        audit_builder = getattr(strategy, "build_decision_audit", None)
        if callable(audit_builder):
            audit = audit_builder(event, signal)
            input_snapshot = audit.input_snapshot
            signal_snapshot = audit.signal_snapshot
            reason_summary = audit.reason_summary

        self._runtime_state.record_strategy_decision(
            strategy_id=signal.strategy_id,
            decision_at=signal.created_at,
            input_snapshot=input_snapshot,
            signal_snapshot=signal_snapshot,
            reason_summary=reason_summary,
        )
        self._logger.info(
            "strategy_signal_generated",
            trader_run_id=self._runtime_state.trader_run_id,
            instance_id=self._runtime_state.instance_id,
            strategy_id=signal.strategy_id,
            exchange=signal.exchange,
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            input_snapshot=input_snapshot,
            signal_snapshot=signal_snapshot,
            reason_summary=reason_summary,
        )


def build_default_trader_service(
    settings: Settings,
    *,
    strategy: StrategyPort | None = None,
    pipeline: TraderPipelinePorts | None = None,
) -> TraderService:
    """Build the default trader runtime entrypoint used by the CLI."""
    collector = build_default_collector_service(
        exchange=settings.exchange,
        symbols=settings.symbols,
        timeframe=settings.primary_timeframe,
        market_data_source=settings.market_data_source,
        symbol_rules=settings.symbol_rules,
    )
    source = CollectorBarEventSource(collector)
    engine = create_database_engine(settings=settings)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory)
    observability = build_observability(
        settings=settings,
        service="trader",
        logger_name="signalark.trader.control_plane",
    )
    control_runtime = TraderControlRuntime(
        control_store,
        account_id=settings.account_id,
        timeframe=settings.primary_timeframe,
        market_stale_threshold_seconds=settings.market_stale_threshold_seconds,
        lease_ttl_seconds=settings.lease_ttl_seconds,
        heartbeat_interval_seconds=settings.lease_heartbeat_interval_seconds,
        observability=observability,
    )
    resolved_pipeline = pipeline or TraderPipelinePorts()
    if strategy is not None:
        if resolved_pipeline.strategy is not None:
            raise ValueError("pipeline.strategy and strategy cannot both be provided")
        if resolved_pipeline.risk is not None:
            raise ValueError("pipeline.risk and strategy cannot both be provided")
        resolved_pipeline.strategy = strategy
    elif (
        resolved_pipeline.strategy is None
        and resolved_pipeline.risk is None
        and resolved_pipeline.oms is None
    ):
        resolved_pipeline.strategy = build_strategy(
            strategy_id=settings.primary_strategy_id,
            account_id=settings.account_id,
        )

    if resolved_pipeline.strategy is not None and resolved_pipeline.risk is None:
        oms_service = build_default_trader_oms_service(
            settings=settings,
            session_factory=session_factory,
            control_store=control_store,
            observability=observability,
        )
        resolved_pipeline.risk = OmsSignalRiskRouter(
            oms_service=oms_service,
            symbol_rules=settings.symbol_rules,
            control_runtime=control_runtime,
        )
    reconciliation_oms_service = build_default_trader_oms_service(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        observability=observability,
    )
    reconciliation_runtime = TraderReconciliationRuntime(
        SessionFactoryBackedReconciliationStore(session_factory),
        oms_service=reconciliation_oms_service,
        control_store=control_store,
        account_id=settings.account_id,
        exchange=settings.exchange,
        cost_model=settings.paper_cost_model,
        control_runtime=control_runtime,
        observability=observability,
        reconciliation_interval_seconds=60,
    )
    return TraderService(
        source,
        pipeline=resolved_pipeline,
        control_runtime=control_runtime,
        reconciliation_runtime=reconciliation_runtime,
        bind_run_id_to_logs=settings.trader_run_id_bind_to_logs,
    )


def _default_strategy_input_snapshot(event: BarEvent) -> dict[str, str | None]:
    market_state = event.market_state
    snapshot = {
        "bar_key": event.bar_key,
        "source_kind": event.source_kind,
        "bar_start_time": event.bar_start_time.isoformat(),
        "bar_end_time": event.bar_end_time.isoformat(),
        "close": str(event.close),
        "trade_date": market_state.trade_date.isoformat() if market_state is not None else None,
        "trading_phase": market_state.trading_phase.value if market_state is not None else None,
        "previous_close": str(market_state.previous_close) if market_state is not None else None,
    }
    return snapshot


def _default_signal_snapshot(signal: Signal) -> dict[str, str]:
    return {
        "signal_id": str(signal.id),
        "signal_type": signal.signal_type.value,
        "target_position": str(signal.target_position),
        "event_time": signal.event_time.isoformat(),
        "created_at": signal.created_at.isoformat(),
    }
