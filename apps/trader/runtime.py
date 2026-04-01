"""Lifecycle and runtime-state helpers for the trader process."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import uuid4

from src.domain.events import BarEvent
from src.domain.risk import RiskControlState, resolve_risk_control_state
from src.shared.types import shanghai_now

LifecycleStatus = Literal["created", "starting", "running", "stopping", "stopped"]
HealthStatus = Literal["booting", "alive", "draining", "stopped"]
ReadinessStatus = Literal["not_ready", "ready", "draining"]
IntegrationStatus = Literal["reserved", "bound"]
SingleActiveStatus = Literal["unbound", "observed", "acquired", "lost", "rejected"]


def default_instance_id() -> str:
    """Return the stable local process identity reserved for future leases."""
    return f"{socket.gethostname()}:{os.getpid()}"


@dataclass(slots=True)
class IntegrationPointState:
    """Track whether a downstream integration point is reserved or bound."""

    status: IntegrationStatus = "reserved"
    handler_name: str | None = None

    def bind(self, handler_name: str) -> None:
        self.status = "bound"
        self.handler_name = handler_name

    def snapshot(self) -> dict[str, object]:
        return {
            "status": self.status,
            "handler_name": self.handler_name,
        }


@dataclass(slots=True)
class SingleActiveState:
    """Reserve fields required by the future PostgreSQL lease mechanism."""

    status: SingleActiveStatus = "unbound"
    owner_instance_id: str | None = None
    fencing_token: int | None = None
    lease_expires_at: datetime | None = None
    last_heartbeat_at: datetime | None = None

    def observe(
        self,
        *,
        owner_instance_id: str,
        fencing_token: int,
        lease_expires_at: datetime,
        last_heartbeat_at: datetime,
        status: SingleActiveStatus = "observed",
    ) -> None:
        self.status = status
        self.owner_instance_id = owner_instance_id
        self.fencing_token = fencing_token
        self.lease_expires_at = lease_expires_at
        self.last_heartbeat_at = last_heartbeat_at

    def mark_lost(self, *, owner_instance_id: str | None = None) -> None:
        self.status = "lost"
        self.owner_instance_id = owner_instance_id

    def mark_rejected(
        self,
        *,
        owner_instance_id: str | None,
        fencing_token: int | None,
        lease_expires_at: datetime | None,
        last_heartbeat_at: datetime | None,
    ) -> None:
        self.status = "rejected"
        self.owner_instance_id = owner_instance_id
        self.fencing_token = fencing_token
        self.lease_expires_at = lease_expires_at
        self.last_heartbeat_at = last_heartbeat_at

    def snapshot(self) -> dict[str, object]:
        return {
            "status": self.status,
            "owner_instance_id": self.owner_instance_id,
            "fencing_token": self.fencing_token,
            "lease_expires_at": _isoformat(self.lease_expires_at),
            "last_heartbeat_at": _isoformat(self.last_heartbeat_at),
        }


@dataclass(slots=True)
class PipelineState:
    """Expose future strategy/risk/OMS binding state to the control plane."""

    strategy: IntegrationPointState = field(default_factory=IntegrationPointState)
    risk: IntegrationPointState = field(default_factory=IntegrationPointState)
    oms: IntegrationPointState = field(default_factory=IntegrationPointState)

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {
            "strategy": self.strategy.snapshot(),
            "risk": self.risk.snapshot(),
            "oms": self.oms.snapshot(),
        }


@dataclass(slots=True)
class TraderRuntimeState:
    """Process-scoped state that later health/readiness APIs can expose."""

    trader_run_id: str = field(default_factory=lambda: str(uuid4()))
    instance_id: str = field(default_factory=default_instance_id)
    account_id: str | None = None
    status: LifecycleStatus = "created"
    health_status: HealthStatus = "booting"
    readiness_status: ReadinessStatus = "not_ready"
    readiness_reason: str | None = None
    control_state: RiskControlState = RiskControlState.NORMAL
    strategy_enabled: bool = True
    kill_switch_active: bool = False
    protection_mode_active: bool = False
    market_data_fresh: bool = False
    latest_final_bar_time: datetime | None = None
    current_trading_phase: str | None = None
    started_at: datetime | None = None
    ready_at: datetime | None = None
    stopping_at: datetime | None = None
    stopped_at: datetime | None = None
    stop_reason: str | None = None
    last_event_at: datetime | None = None
    last_event_type: str | None = None
    last_bar_key: str | None = None
    last_strategy_bar_key: str | None = None
    last_ignored_bar_key: str | None = None
    last_ignored_bar_reason: str | None = None
    pipeline: PipelineState = field(default_factory=PipelineState)
    single_active: SingleActiveState = field(default_factory=SingleActiveState)

    def mark_starting(self) -> None:
        now = shanghai_now()
        self.status = "starting"
        self.health_status = "booting"
        self.readiness_status = "not_ready"
        self.readiness_reason = "starting"
        self.started_at = now
        self.ready_at = None
        self.stop_reason = None
        self.stopping_at = None
        self.stopped_at = None

    def mark_running(self, *, ready: bool = True) -> None:
        now = shanghai_now()
        self.status = "running"
        self.health_status = "alive"
        if ready:
            self.readiness_status = "ready"
            self.readiness_reason = None
            self.ready_at = now
            return

        self.readiness_status = "not_ready"
        self.readiness_reason = "runtime_started_waiting_for_order_submission_readiness"
        self.ready_at = None

    def mark_stopping(self, reason: str) -> None:
        now = shanghai_now()
        self.status = "stopping"
        self.health_status = "draining"
        self.readiness_status = "draining"
        self.readiness_reason = reason
        self.stop_reason = reason
        self.stopping_at = now

    def mark_stopped(self, reason: str) -> None:
        now = shanghai_now()
        self.status = "stopped"
        self.health_status = "stopped"
        self.readiness_status = "not_ready"
        self.readiness_reason = reason
        self.stop_reason = reason
        self.stopped_at = now

    def set_readiness(self, *, ready: bool, reason: str | None = None) -> None:
        now = shanghai_now()
        if ready:
            self.readiness_status = "ready"
            self.readiness_reason = None
            if self.ready_at is None:
                self.ready_at = now
            return

        self.readiness_status = "not_ready"
        self.readiness_reason = reason
        self.ready_at = None

    def apply_control_state(
        self,
        *,
        strategy_enabled: bool,
        kill_switch_active: bool,
        protection_mode_active: bool,
    ) -> None:
        self.strategy_enabled = strategy_enabled
        self.kill_switch_active = kill_switch_active
        self.protection_mode_active = protection_mode_active
        self.control_state = resolve_risk_control_state(
            strategy_enabled=strategy_enabled,
            kill_switch_active=kill_switch_active,
            protection_mode_active=protection_mode_active,
        )

    def update_market_observation(
        self,
        *,
        latest_final_bar_time: datetime | None,
        current_trading_phase: str | None,
        market_data_fresh: bool,
    ) -> None:
        self.latest_final_bar_time = latest_final_bar_time
        self.current_trading_phase = current_trading_phase
        self.market_data_fresh = market_data_fresh

    def record_event(self, event: object) -> None:
        self.last_event_at = shanghai_now()
        self.last_event_type = type(event).__name__
        if isinstance(event, BarEvent):
            self.last_bar_key = event.bar_key

    def record_strategy_bar(self, event: BarEvent) -> None:
        self.last_strategy_bar_key = event.bar_key

    def record_ignored_bar(self, event: BarEvent, reason: str) -> None:
        self.last_ignored_bar_key = event.bar_key
        self.last_ignored_bar_reason = reason

    def health_payload(self, *, event_bus_pending_count: int) -> dict[str, object]:
        return {
            "status": self.health_status,
            "trader_run_id": self.trader_run_id,
            "instance_id": self.instance_id,
            "account_id": self.account_id,
            "lifecycle": self.status,
            "event_bus_pending_count": event_bus_pending_count,
            "last_event_at": _isoformat(self.last_event_at),
        }

    def readiness_payload(self, *, event_bus_pending_count: int) -> dict[str, object]:
        market_state_available = self.current_trading_phase is not None
        return {
            "status": self.readiness_status,
            "trader_run_id": self.trader_run_id,
            "instance_id": self.instance_id,
            "account_id": self.account_id,
            "event_bus_pending_count": event_bus_pending_count,
            "control_state": self.control_state.value,
            "strategy_enabled": self.strategy_enabled,
            "kill_switch_active": self.kill_switch_active,
            "protection_mode_active": self.protection_mode_active,
            "market_data_fresh": self.market_data_fresh,
            "market_state_available": market_state_available,
            "latest_final_bar_time": _isoformat(self.latest_final_bar_time),
            "current_trading_phase": self.current_trading_phase,
            "reason": self.readiness_reason,
            "pipeline": self.pipeline.snapshot(),
            "single_active": self.single_active.snapshot(),
            "last_strategy_bar_key": self.last_strategy_bar_key,
            "last_ignored_bar_reason": self.last_ignored_bar_reason,
        }

    def snapshot(self, *, event_bus_pending_count: int) -> dict[str, object]:
        market_state_available = self.current_trading_phase is not None
        return {
            "trader_run_id": self.trader_run_id,
            "instance_id": self.instance_id,
            "account_id": self.account_id,
            "status": self.status,
            "health_status": self.health_status,
            "readiness_status": self.readiness_status,
            "readiness_reason": self.readiness_reason,
            "control_state": self.control_state.value,
            "strategy_enabled": self.strategy_enabled,
            "kill_switch_active": self.kill_switch_active,
            "protection_mode_active": self.protection_mode_active,
            "market_data_fresh": self.market_data_fresh,
            "market_state_available": market_state_available,
            "latest_final_bar_time": _isoformat(self.latest_final_bar_time),
            "current_trading_phase": self.current_trading_phase,
            "started_at": _isoformat(self.started_at),
            "ready_at": _isoformat(self.ready_at),
            "stopping_at": _isoformat(self.stopping_at),
            "stopped_at": _isoformat(self.stopped_at),
            "stop_reason": self.stop_reason,
            "last_event_at": _isoformat(self.last_event_at),
            "last_event_type": self.last_event_type,
            "last_bar_key": self.last_bar_key,
            "last_strategy_bar_key": self.last_strategy_bar_key,
            "last_ignored_bar_key": self.last_ignored_bar_key,
            "last_ignored_bar_reason": self.last_ignored_bar_reason,
            "event_bus_pending_count": event_bus_pending_count,
            "pipeline": self.pipeline.snapshot(),
            "single_active": self.single_active.snapshot(),
        }


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
