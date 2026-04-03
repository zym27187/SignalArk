"""DB-backed operator controls, single-active lease, and trader runtime status."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, inspect, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker
from src.domain.events import BarEvent
from src.domain.market import timeframe_to_timedelta
from src.domain.risk import RiskControlState, resolve_risk_control_state
from src.infra.db.base import Base
from src.infra.db.session import session_scope
from src.infra.observability import SignalArkObservability
from src.shared.types import SHANGHAI_TIMEZONE, shanghai_now

if TYPE_CHECKING:
    from apps.trader.runtime import TraderRuntimeState


LEASE_TABLE_NAME = "trader_account_leases"
CONTROL_TABLE_NAME = "trader_controls"
RUNTIME_STATUS_TABLE_NAME = "trader_runtime_status"
CONTROL_PLANE_TABLE_NAMES = frozenset(
    {
        CONTROL_TABLE_NAME,
        LEASE_TABLE_NAME,
        RUNTIME_STATUS_TABLE_NAME,
    }
)


class MissingControlPlaneSchemaError(RuntimeError):
    """Raised when the migrated control-plane tables are unavailable."""

    def __init__(self, missing_tables: set[str]) -> None:
        message = (
            "Control-plane schema is missing required tables: "
            f"{', '.join(sorted(missing_tables))}. "
            "Run `.venv/bin/alembic -c migrations/alembic.ini upgrade head` first."
        )
        super().__init__(message)
        self.missing_tables = frozenset(missing_tables)


class TraderControlRecord(Base):
    """Persist the operator-facing control switches for one account."""

    __tablename__ = CONTROL_TABLE_NAME

    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    strategy_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    kill_switch_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    protection_mode_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancel_all_token: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_cancel_all_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TraderAccountLeaseRecord(Base):
    """Persist the account-scoped single-active trader lease."""

    __tablename__ = LEASE_TABLE_NAME

    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_instance_id: Mapped[str | None] = mapped_column(String(255))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fencing_token: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TraderRuntimeStatusRecord(Base):
    """Persist the latest trader runtime view that the API can expose."""

    __tablename__ = RUNTIME_STATUS_TABLE_NAME

    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trader_run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    instance_id: Mapped[str] = mapped_column(String(255), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False)
    health_status: Mapped[str] = mapped_column(String(32), nullable=False)
    readiness_status: Mapped[str] = mapped_column(String(32), nullable=False)
    control_state: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    kill_switch_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    protection_mode_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    market_data_fresh: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latest_final_bar_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_trading_phase: Mapped[str | None] = mapped_column(String(64))
    last_seen_bars_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    last_strategy_bars_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    fencing_token: Mapped[int | None] = mapped_column(Integer)
    last_status_message: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class TraderControlSnapshot:
    """Typed operator-control view shared between trader and API."""

    account_id: str
    strategy_enabled: bool = True
    kill_switch_active: bool = False
    protection_mode_active: bool = False
    cancel_all_token: int = 0
    last_cancel_all_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def control_state(self) -> RiskControlState:
        return resolve_risk_control_state(
            strategy_enabled=self.strategy_enabled,
            kill_switch_active=self.kill_switch_active,
            protection_mode_active=self.protection_mode_active,
        )


@dataclass(frozen=True, slots=True)
class TraderLeaseSnapshot:
    """Typed account-lease view shared across operator and trader code."""

    account_id: str
    owner_instance_id: str | None = None
    lease_expires_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    fencing_token: int | None = None

    def is_held_by(self, *, instance_id: str, as_of: datetime) -> bool:
        return (
            self.owner_instance_id == instance_id
            and self.lease_expires_at is not None
            and self.lease_expires_at > as_of
        )

    def expired(self, *, as_of: datetime) -> bool:
        return self.lease_expires_at is None or self.lease_expires_at <= as_of


@dataclass(frozen=True, slots=True)
class TraderRuntimeStatusSnapshot:
    """The last persisted trader runtime view used by status APIs."""

    account_id: str
    trader_run_id: str
    instance_id: str
    lifecycle_status: str
    health_status: str
    readiness_status: str
    control_state: RiskControlState
    strategy_enabled: bool
    kill_switch_active: bool
    protection_mode_active: bool
    market_data_fresh: bool
    latest_final_bar_time: datetime | None
    current_trading_phase: str | None
    fencing_token: int | None
    last_status_message: str | None
    updated_at: datetime
    last_seen_bars: dict[str, dict[str, object]] = field(default_factory=dict)
    last_strategy_bars: dict[str, dict[str, object]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LeaseActionResult:
    """Result of one acquire/heartbeat/release lease operation."""

    accepted: bool
    snapshot: TraderLeaseSnapshot
    message: str


@dataclass(frozen=True, slots=True)
class SubmissionLeaseGuard:
    """Carry the current fencing token into new-order submission paths."""

    account_id: str
    instance_id: str
    fencing_token: int


def _control_snapshot_from_record(record: TraderControlRecord) -> TraderControlSnapshot:
    return TraderControlSnapshot(
        account_id=record.account_id,
        strategy_enabled=record.strategy_enabled,
        kill_switch_active=record.kill_switch_active,
        protection_mode_active=record.protection_mode_active,
        cancel_all_token=record.cancel_all_token,
        last_cancel_all_at=_shanghai_datetime(record.last_cancel_all_at),
        updated_at=_shanghai_datetime(record.updated_at),
    )


def _lease_snapshot_from_record(record: TraderAccountLeaseRecord) -> TraderLeaseSnapshot:
    return TraderLeaseSnapshot(
        account_id=record.account_id,
        owner_instance_id=record.owner_instance_id,
        lease_expires_at=_shanghai_datetime(record.lease_expires_at),
        last_heartbeat_at=_shanghai_datetime(record.last_heartbeat_at),
        fencing_token=record.fencing_token,
    )


def _runtime_status_from_record(record: TraderRuntimeStatusRecord) -> TraderRuntimeStatusSnapshot:
    return TraderRuntimeStatusSnapshot(
        account_id=record.account_id,
        trader_run_id=record.trader_run_id,
        instance_id=record.instance_id,
        lifecycle_status=record.lifecycle_status,
        health_status=record.health_status,
        readiness_status=record.readiness_status,
        control_state=RiskControlState(record.control_state),
        strategy_enabled=record.strategy_enabled,
        kill_switch_active=record.kill_switch_active,
        protection_mode_active=record.protection_mode_active,
        market_data_fresh=record.market_data_fresh,
        latest_final_bar_time=_shanghai_datetime(record.latest_final_bar_time),
        current_trading_phase=record.current_trading_phase,
        last_seen_bars=_json_object_mapping(record.last_seen_bars_json),
        last_strategy_bars=_json_object_mapping(record.last_strategy_bars_json),
        fencing_token=record.fencing_token,
        last_status_message=record.last_status_message,
        updated_at=_shanghai_datetime(record.updated_at) or shanghai_now(),
    )


class TraderControlPlaneStore:
    """Persist and query the shared control-plane state."""

    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        clock=shanghai_now,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return

        existing_tables = set(inspect(self._engine()).get_table_names())
        missing_tables = set(CONTROL_PLANE_TABLE_NAMES - existing_tables)
        if missing_tables:
            raise MissingControlPlaneSchemaError(missing_tables)
        self._schema_ready = True

    def ping(self) -> bool:
        self.ensure_schema()
        with session_scope(self._session_factory) as session:
            session.execute(select(1))
        return True

    def get_control_snapshot(self, account_id: str) -> TraderControlSnapshot:
        self.ensure_schema()
        with session_scope(self._session_factory) as session:
            record = session.get(TraderControlRecord, account_id)
            if record is None:
                now = self._clock()
                record = TraderControlRecord(
                    account_id=account_id,
                    strategy_enabled=True,
                    kill_switch_active=False,
                    protection_mode_active=False,
                    cancel_all_token=0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
                session.flush()
            return _control_snapshot_from_record(record)

    def set_strategy_enabled(
        self,
        *,
        account_id: str,
        enabled: bool,
    ) -> TraderControlSnapshot:
        return self._mutate_control(
            account_id=account_id,
            mutation=lambda record, now: (
                setattr(record, "strategy_enabled", enabled),
                setattr(record, "updated_at", now),
            ),
        )

    def set_kill_switch(
        self,
        *,
        account_id: str,
        active: bool,
    ) -> TraderControlSnapshot:
        return self._mutate_control(
            account_id=account_id,
            mutation=lambda record, now: (
                setattr(record, "kill_switch_active", active),
                setattr(record, "updated_at", now),
            ),
        )

    def set_protection_mode(
        self,
        *,
        account_id: str,
        active: bool,
    ) -> TraderControlSnapshot:
        return self._mutate_control(
            account_id=account_id,
            mutation=lambda record, now: (
                setattr(record, "protection_mode_active", active),
                setattr(record, "updated_at", now),
            ),
        )

    def mark_cancel_all_requested(self, *, account_id: str) -> TraderControlSnapshot:
        return self._mutate_control(
            account_id=account_id,
            mutation=lambda record, now: (
                setattr(record, "cancel_all_token", record.cancel_all_token + 1),
                setattr(record, "last_cancel_all_at", now),
                setattr(record, "updated_at", now),
            ),
        )

    def load_lease_snapshot(self, account_id: str) -> TraderLeaseSnapshot:
        self.ensure_schema()
        with session_scope(self._session_factory) as session:
            record = session.get(TraderAccountLeaseRecord, account_id)
            if record is None:
                return TraderLeaseSnapshot(account_id=account_id)
            return _lease_snapshot_from_record(record)

    def acquire_lease(
        self,
        *,
        account_id: str,
        instance_id: str,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> LeaseActionResult:
        self.ensure_schema()
        now = now or self._clock()
        lease_expires_at = now + timedelta(seconds=ttl_seconds)
        with session_scope(self._session_factory) as session:
            record = session.get(TraderAccountLeaseRecord, account_id)
            if record is None:
                record = TraderAccountLeaseRecord(
                    account_id=account_id,
                    owner_instance_id=instance_id,
                    lease_expires_at=lease_expires_at,
                    last_heartbeat_at=now,
                    fencing_token=1,
                    updated_at=now,
                )
                session.add(record)
                session.flush()
                return LeaseActionResult(
                    accepted=True,
                    snapshot=_lease_snapshot_from_record(record),
                    message="lease_acquired",
                )

            current_snapshot = _lease_snapshot_from_record(record)
            if current_snapshot.is_held_by(instance_id=instance_id, as_of=now):
                record.lease_expires_at = lease_expires_at
                record.last_heartbeat_at = now
                record.updated_at = now
                session.flush()
                return LeaseActionResult(
                    accepted=True,
                    snapshot=_lease_snapshot_from_record(record),
                    message="lease_renewed",
                )

            if current_snapshot.expired(as_of=now) or current_snapshot.owner_instance_id is None:
                record.owner_instance_id = instance_id
                record.lease_expires_at = lease_expires_at
                record.last_heartbeat_at = now
                record.fencing_token = (record.fencing_token or 0) + 1
                record.updated_at = now
                session.flush()
                return LeaseActionResult(
                    accepted=True,
                    snapshot=_lease_snapshot_from_record(record),
                    message="lease_taken_over",
                )

            return LeaseActionResult(
                accepted=False,
                snapshot=current_snapshot,
                message="lease_held_by_other_instance",
            )

    def heartbeat_lease(
        self,
        *,
        account_id: str,
        instance_id: str,
        fencing_token: int,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> LeaseActionResult:
        self.ensure_schema()
        now = now or self._clock()
        lease_expires_at = now + timedelta(seconds=ttl_seconds)
        with session_scope(self._session_factory) as session:
            result = session.execute(
                update(TraderAccountLeaseRecord)
                .where(TraderAccountLeaseRecord.account_id == account_id)
                .where(TraderAccountLeaseRecord.owner_instance_id == instance_id)
                .where(TraderAccountLeaseRecord.fencing_token == fencing_token)
                .where(TraderAccountLeaseRecord.lease_expires_at.is_not(None))
                .where(TraderAccountLeaseRecord.lease_expires_at > now)
                .values(
                    lease_expires_at=lease_expires_at,
                    last_heartbeat_at=now,
                    updated_at=now,
                )
            )
            record = session.get(TraderAccountLeaseRecord, account_id)
            snapshot = (
                TraderLeaseSnapshot(account_id=account_id)
                if record is None
                else _lease_snapshot_from_record(record)
            )
            return LeaseActionResult(
                accepted=result.rowcount == 1,
                snapshot=snapshot,
                message=(
                    "lease_heartbeat_accepted"
                    if result.rowcount == 1
                    else "lease_heartbeat_rejected"
                ),
            )

    def release_lease(
        self,
        *,
        account_id: str,
        instance_id: str,
        fencing_token: int | None,
        now: datetime | None = None,
    ) -> LeaseActionResult:
        self.ensure_schema()
        now = now or self._clock()
        with session_scope(self._session_factory) as session:
            query = (
                update(TraderAccountLeaseRecord)
                .where(TraderAccountLeaseRecord.account_id == account_id)
                .where(TraderAccountLeaseRecord.owner_instance_id == instance_id)
                .values(
                    owner_instance_id=None,
                    lease_expires_at=now,
                    last_heartbeat_at=now,
                    updated_at=now,
                )
            )
            if fencing_token is not None:
                query = query.where(TraderAccountLeaseRecord.fencing_token == fencing_token)

            result = session.execute(query)
            record = session.get(TraderAccountLeaseRecord, account_id)
            snapshot = (
                TraderLeaseSnapshot(account_id=account_id)
                if record is None
                else _lease_snapshot_from_record(record)
            )
            return LeaseActionResult(
                accepted=result.rowcount == 1,
                snapshot=snapshot,
                message="lease_released" if result.rowcount == 1 else "lease_release_skipped",
            )

    def validate_submission_lease(
        self,
        *,
        account_id: str,
        instance_id: str,
        fencing_token: int,
        now: datetime | None = None,
    ) -> LeaseActionResult:
        now = now or self._clock()
        snapshot = self.load_lease_snapshot(account_id)
        if snapshot.fencing_token != fencing_token:
            return LeaseActionResult(
                accepted=False,
                snapshot=snapshot,
                message="fencing_token_mismatch",
            )
        if not snapshot.is_held_by(instance_id=instance_id, as_of=now):
            return LeaseActionResult(
                accepted=False,
                snapshot=snapshot,
                message="lease_not_held_by_instance",
            )
        return LeaseActionResult(
            accepted=True,
            snapshot=snapshot,
            message="lease_valid_for_submission",
        )

    def save_runtime_status(
        self,
        snapshot: TraderRuntimeStatusSnapshot,
    ) -> TraderRuntimeStatusSnapshot:
        self.ensure_schema()
        with session_scope(self._session_factory) as session:
            record = session.get(TraderRuntimeStatusRecord, snapshot.account_id)
            if record is None:
                record = TraderRuntimeStatusRecord(
                    account_id=snapshot.account_id,
                    trader_run_id=snapshot.trader_run_id,
                    instance_id=snapshot.instance_id,
                    lifecycle_status=snapshot.lifecycle_status,
                    health_status=snapshot.health_status,
                    readiness_status=snapshot.readiness_status,
                    control_state=snapshot.control_state.value,
                    strategy_enabled=snapshot.strategy_enabled,
                    kill_switch_active=snapshot.kill_switch_active,
                    protection_mode_active=snapshot.protection_mode_active,
                    market_data_fresh=snapshot.market_data_fresh,
                    latest_final_bar_time=snapshot.latest_final_bar_time,
                    current_trading_phase=snapshot.current_trading_phase,
                    last_seen_bars_json=snapshot.last_seen_bars,
                    last_strategy_bars_json=snapshot.last_strategy_bars,
                    fencing_token=snapshot.fencing_token,
                    last_status_message=snapshot.last_status_message,
                    updated_at=snapshot.updated_at,
                )
                session.add(record)
                session.flush()
                return _runtime_status_from_record(record)

            record.trader_run_id = snapshot.trader_run_id
            record.instance_id = snapshot.instance_id
            record.lifecycle_status = snapshot.lifecycle_status
            record.health_status = snapshot.health_status
            record.readiness_status = snapshot.readiness_status
            record.control_state = snapshot.control_state.value
            record.strategy_enabled = snapshot.strategy_enabled
            record.kill_switch_active = snapshot.kill_switch_active
            record.protection_mode_active = snapshot.protection_mode_active
            record.market_data_fresh = snapshot.market_data_fresh
            record.latest_final_bar_time = snapshot.latest_final_bar_time
            record.current_trading_phase = snapshot.current_trading_phase
            record.last_seen_bars_json = snapshot.last_seen_bars
            record.last_strategy_bars_json = snapshot.last_strategy_bars
            record.fencing_token = snapshot.fencing_token
            record.last_status_message = snapshot.last_status_message
            record.updated_at = snapshot.updated_at
            session.flush()
            return _runtime_status_from_record(record)

    def load_runtime_status(self, account_id: str) -> TraderRuntimeStatusSnapshot | None:
        self.ensure_schema()
        with session_scope(self._session_factory) as session:
            record = session.get(TraderRuntimeStatusRecord, account_id)
            return None if record is None else _runtime_status_from_record(record)

    def build_status_view(
        self,
        *,
        account_id: str,
        timeframe: str,
        market_stale_threshold_seconds: int,
        as_of: datetime | None = None,
    ) -> dict[str, object]:
        self.ensure_schema()
        as_of = as_of or self._clock()
        control_snapshot = self.get_control_snapshot(account_id)
        lease_snapshot = self.load_lease_snapshot(account_id)
        runtime_status = self.load_runtime_status(account_id)
        market_data_fresh = False
        latest_final_bar_time = None
        current_trading_phase = None
        trader_run_id = None
        instance_id = None
        readiness_status = "not_ready"
        health_status = "unknown"
        lifecycle_status = "stopped"
        status_message = None

        if runtime_status is not None:
            threshold = max(
                timeframe_to_timedelta(timeframe) * 2,
                timedelta(seconds=market_stale_threshold_seconds),
            )
            latest_final_bar_time = runtime_status.latest_final_bar_time
            current_trading_phase = runtime_status.current_trading_phase
            trader_run_id = runtime_status.trader_run_id
            instance_id = runtime_status.instance_id
            health_status = runtime_status.health_status
            lifecycle_status = runtime_status.lifecycle_status
            status_message = runtime_status.last_status_message
            readiness_status = runtime_status.readiness_status
            market_data_fresh = (
                latest_final_bar_time is not None and as_of - latest_final_bar_time <= threshold
            )
        market_state_available = current_trading_phase is not None

        lease_valid = (
            instance_id is not None
            and runtime_status is not None
            and lease_snapshot.is_held_by(instance_id=instance_id, as_of=as_of)
            and lease_snapshot.fencing_token == runtime_status.fencing_token
        )
        ready = (
            runtime_status is not None
            and lifecycle_status == "running"
            and health_status == "alive"
            and readiness_status == "ready"
            and market_data_fresh
            and market_state_available
            and lease_valid
        )
        return {
            "trader_run_id": trader_run_id,
            "instance_id": instance_id,
            "account_id": account_id,
            "control_state": control_snapshot.control_state.value,
            "strategy_enabled": control_snapshot.strategy_enabled,
            "kill_switch_active": control_snapshot.kill_switch_active,
            "protection_mode_active": control_snapshot.protection_mode_active,
            "ready": ready,
            "status": "ready" if ready else "not_ready",
            "health_status": health_status,
            "lifecycle_status": lifecycle_status,
            "market_data_fresh": market_data_fresh,
            "market_state_available": market_state_available,
            "latest_final_bar_time": _isoformat(latest_final_bar_time),
            "current_trading_phase": current_trading_phase,
            "lease_owner_instance_id": lease_snapshot.owner_instance_id,
            "lease_expires_at": _isoformat(lease_snapshot.lease_expires_at),
            "last_heartbeat_at": _isoformat(lease_snapshot.last_heartbeat_at),
            "fencing_token": lease_snapshot.fencing_token,
            "last_cancel_all_at": _isoformat(control_snapshot.last_cancel_all_at),
            "cancel_all_token": control_snapshot.cancel_all_token,
            "message": status_message,
            "as_of": _isoformat(as_of),
        }

    def _mutate_control(
        self,
        *,
        account_id: str,
        mutation,
    ) -> TraderControlSnapshot:
        self.ensure_schema()
        with session_scope(self._session_factory) as session:
            record = session.get(TraderControlRecord, account_id)
            if record is None:
                now = self._clock()
                record = TraderControlRecord(
                    account_id=account_id,
                    strategy_enabled=True,
                    kill_switch_active=False,
                    protection_mode_active=False,
                    cancel_all_token=0,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
                session.flush()
            mutation(record, self._clock())
            session.flush()
            return _control_snapshot_from_record(record)

    def _engine(self) -> Engine:
        bind = self._session_factory.kw.get("bind")
        if bind is None:
            raise RuntimeError("session_factory must be bound to an engine")
        return bind


class TraderControlRuntime:
    """Drive trader readiness from DB-backed lease and operator controls."""

    def __init__(
        self,
        store: TraderControlPlaneStore,
        *,
        account_id: str,
        timeframe: str,
        market_stale_threshold_seconds: int,
        lease_ttl_seconds: int,
        heartbeat_interval_seconds: int,
        observability: SignalArkObservability | None = None,
        clock=shanghai_now,
        enable_background_task: bool = True,
    ) -> None:
        self._store = store
        self._account_id = account_id
        self._timeframe = timeframe
        self._market_stale_threshold_seconds = market_stale_threshold_seconds
        self._lease_ttl_seconds = lease_ttl_seconds
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._clock = clock
        self._enable_background_task = enable_background_task
        self._observability = observability or SignalArkObservability(
            service="trader",
            logger_name="signalark.trader.control_plane",
            clock=clock,
        )
        self._runtime_state: TraderRuntimeState | None = None
        self._control_snapshot = TraderControlSnapshot(account_id=account_id)
        self._lease_snapshot = TraderLeaseSnapshot(account_id=account_id)
        self._latest_final_bar_time: datetime | None = None
        self._current_trading_phase: str | None = None
        self._last_status_message: str | None = None
        self._not_ready_since: datetime | None = None
        self._not_ready_alert_emitted = False
        self._market_stale_cycles = 0
        self._stop_event = asyncio.Event()
        self._background_task: asyncio.Task[None] | None = None

    @property
    def control_state(self) -> RiskControlState:
        return self._control_snapshot.control_state

    def submission_guard(self) -> SubmissionLeaseGuard | None:
        if self._runtime_state is None:
            return None
        as_of = self._clock()
        if (
            self._runtime_state.readiness_status != "ready"
            or self._lease_snapshot.fencing_token is None
            or not self._lease_snapshot.is_held_by(
                instance_id=self._runtime_state.instance_id,
                as_of=as_of,
            )
        ):
            return None
        return SubmissionLeaseGuard(
            account_id=self._account_id,
            instance_id=self._runtime_state.instance_id,
            fencing_token=self._lease_snapshot.fencing_token,
        )

    async def start(self, runtime_state: TraderRuntimeState) -> None:
        self._runtime_state = runtime_state
        self._runtime_state.account_id = self._account_id
        self._store.ensure_schema()
        self._apply_control_snapshot(self._store.get_control_snapshot(self._account_id))
        lease_result = self._store.acquire_lease(
            account_id=self._account_id,
            instance_id=self._runtime_state.instance_id,
            ttl_seconds=self._lease_ttl_seconds,
            now=self._clock(),
        )
        self._lease_snapshot = lease_result.snapshot
        if lease_result.accepted and self._lease_snapshot.fencing_token is not None:
            self._runtime_state.single_active.observe(
                owner_instance_id=self._runtime_state.instance_id,
                fencing_token=self._lease_snapshot.fencing_token,
                lease_expires_at=self._lease_snapshot.lease_expires_at or self._clock(),
                last_heartbeat_at=self._lease_snapshot.last_heartbeat_at or self._clock(),
                status="acquired",
            )
            self._emit(
                event_name="runtime.lease_acquired",
                severity="info",
                message="Trader acquired the single-active submission lease.",
                reason_code=lease_result.message.upper(),
                details={
                    "lease_expires_at": self._lease_snapshot.lease_expires_at,
                    "last_heartbeat_at": self._lease_snapshot.last_heartbeat_at,
                },
            )
        else:
            self._runtime_state.single_active.mark_rejected(
                owner_instance_id=self._lease_snapshot.owner_instance_id,
                fencing_token=self._lease_snapshot.fencing_token,
                lease_expires_at=self._lease_snapshot.lease_expires_at,
                last_heartbeat_at=self._lease_snapshot.last_heartbeat_at,
            )
            self._runtime_state.set_readiness(
                ready=False,
                reason="single_active_lease_unavailable",
            )
            self._last_status_message = lease_result.message
            self._emit(
                event_name="runtime.lease_acquire_rejected",
                severity="warning",
                message="Trader startup could not acquire the single-active submission lease.",
                reason_code="LEASE_UNAVAILABLE",
                details={
                    "lease_owner_instance_id": self._lease_snapshot.owner_instance_id,
                    "lease_expires_at": self._lease_snapshot.lease_expires_at,
                    "fencing_token": self._lease_snapshot.fencing_token,
                },
            )
            await self._persist_runtime_status()
            raise RuntimeError(
                "Single-active trader lease is held by another instance: "
                f"{self._lease_snapshot.owner_instance_id}"
            )

        await self.refresh(reason="startup", force_heartbeat=False)
        if self._enable_background_task:
            self._background_task = asyncio.create_task(
                self._heartbeat_loop(),
                name=f"trader-lease-heartbeat:{self._account_id}",
            )

    async def stop(self, *, reason: str) -> None:
        self._stop_event.set()
        if self._background_task is not None:
            self._background_task.cancel()
            await asyncio.gather(self._background_task, return_exceptions=True)
            self._background_task = None

        if self._runtime_state is None:
            return

        if self._lease_snapshot.fencing_token is not None:
            release_result = self._store.release_lease(
                account_id=self._account_id,
                instance_id=self._runtime_state.instance_id,
                fencing_token=self._lease_snapshot.fencing_token,
                now=self._clock(),
            )
            self._lease_snapshot = release_result.snapshot
        self._runtime_state.single_active.mark_lost(
            owner_instance_id=self._lease_snapshot.owner_instance_id,
        )
        self._runtime_state.set_readiness(ready=False, reason=reason)
        self._last_status_message = reason
        await self._persist_runtime_status()

    async def observe_bar(self, event: BarEvent) -> None:
        if not event.closed or not event.final:
            return
        if self._runtime_state is not None:
            self._runtime_state.record_seen_bar(event)
        self._latest_final_bar_time = event.event_time
        self._current_trading_phase = (
            event.market_state.trading_phase.value if event.market_state is not None else None
        )
        await self.refresh(reason="bar_observed", force_heartbeat=False)

    async def persist_runtime_audit(self) -> None:
        await self._persist_runtime_status()

    async def refresh(self, *, reason: str, force_heartbeat: bool) -> None:
        if self._runtime_state is None:
            return

        as_of = self._clock()
        previous_control_state = self._runtime_state.control_state
        expected_fencing_token = self._lease_snapshot.fencing_token
        lease_was_valid = (
            expected_fencing_token is not None
            and self._runtime_state.single_active.status == "acquired"
            and self._lease_snapshot.owner_instance_id == self._runtime_state.instance_id
        )
        self._apply_control_snapshot(self._store.get_control_snapshot(self._account_id))
        if self._runtime_state.control_state is not previous_control_state:
            self._emit(
                event_name="control.state_changed",
                severity="warning"
                if self._runtime_state.control_state
                in {RiskControlState.KILL_SWITCH, RiskControlState.PROTECTION_MODE}
                else "info",
                message="Trader observed a control-state transition.",
                reason_code=self._runtime_state.control_state.value.upper(),
                details={
                    "previous_control_state": previous_control_state.value,
                    "current_control_state": self._runtime_state.control_state.value,
                    "refresh_reason": reason,
                },
            )
            if self._runtime_state.control_state is RiskControlState.PROTECTION_MODE:
                self._emit(
                    event_name="control.protection_mode_entered",
                    severity="critical",
                    message=(
                        "Trader entered protection mode; only reducing or flattening actions "
                        "remain allowed."
                    ),
                    notify=True,
                    bypass_cooldown=True,
                    reason_code="PROTECTION_MODE_ACTIVE",
                    details={"refresh_reason": reason},
                )
        if expected_fencing_token is not None:
            if force_heartbeat:
                lease_result = self._store.heartbeat_lease(
                    account_id=self._account_id,
                    instance_id=self._runtime_state.instance_id,
                    fencing_token=expected_fencing_token,
                    ttl_seconds=self._lease_ttl_seconds,
                    now=as_of,
                )
                self._lease_snapshot = lease_result.snapshot
                self._last_status_message = lease_result.message
            else:
                self._lease_snapshot = self._store.load_lease_snapshot(self._account_id)
                self._last_status_message = reason

        market_data_fresh = self._market_data_is_fresh(as_of)
        self._runtime_state.update_market_observation(
            latest_final_bar_time=self._latest_final_bar_time,
            current_trading_phase=self._current_trading_phase,
            market_data_fresh=market_data_fresh,
        )

        lease_valid = (
            expected_fencing_token is not None
            and self._lease_snapshot.fencing_token == expected_fencing_token
            and self._lease_snapshot.is_held_by(
                instance_id=self._runtime_state.instance_id,
                as_of=as_of,
            )
        )
        if lease_valid:
            self._runtime_state.single_active.observe(
                owner_instance_id=self._runtime_state.instance_id,
                fencing_token=self._lease_snapshot.fencing_token or expected_fencing_token,
                lease_expires_at=self._lease_snapshot.lease_expires_at or as_of,
                last_heartbeat_at=self._lease_snapshot.last_heartbeat_at or as_of,
                status="acquired",
            )
        else:
            self._runtime_state.single_active.mark_lost(
                owner_instance_id=self._lease_snapshot.owner_instance_id,
            )
        if lease_was_valid and not lease_valid:
            lease_reason_code = (
                "FENCING_TOKEN_INVALID"
                if self._lease_snapshot.fencing_token != expected_fencing_token
                else "LEASE_LOST_OR_EXPIRED"
            )
            self._emit(
                event_name="runtime.lease_lost",
                severity="critical",
                message=(
                    "Trader lost the active submission lease and is no longer ready "
                    "to submit new orders."
                ),
                notify=True,
                bypass_cooldown=True,
                reason_code=lease_reason_code,
                details={
                    "refresh_reason": reason,
                    "lease_owner_instance_id": self._lease_snapshot.owner_instance_id,
                    "lease_expires_at": self._lease_snapshot.lease_expires_at,
                    "expected_fencing_token": expected_fencing_token,
                    "observed_fencing_token": self._lease_snapshot.fencing_token,
                },
            )

        market_state_available = self._current_trading_phase is not None
        ready = (
            self._runtime_state.status == "running"
            and lease_valid
            and market_data_fresh
            and market_state_available
        )
        readiness_reason = None if ready else self._not_ready_reason()
        self._runtime_state.set_readiness(
            ready=ready,
            reason=readiness_reason,
        )
        self._track_runtime_safety(
            as_of=as_of,
            ready=ready,
            readiness_reason=readiness_reason,
            refresh_reason=reason,
        )
        await self._persist_runtime_status()

    async def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._heartbeat_interval_seconds,
                )
                return
            except TimeoutError:
                try:
                    await self.refresh(reason="heartbeat", force_heartbeat=True)
                except Exception as exc:
                    self._emit(
                        event_name="runtime.lease_heartbeat_failed",
                        severity="critical",
                        message="Lease heartbeat failed and trader readiness will be downgraded.",
                        notify=True,
                        bypass_cooldown=True,
                        reason_code="LEASE_HEARTBEAT_FAILED",
                        details={"error": str(exc)},
                    )
                    if self._runtime_state is not None:
                        self._last_status_message = "lease_heartbeat_failed"
                        self._runtime_state.set_readiness(
                            ready=False,
                            reason="lease_heartbeat_failed",
                        )
                        try:
                            await self._persist_runtime_status()
                        except Exception:
                            return

    def _apply_control_snapshot(self, snapshot: TraderControlSnapshot) -> None:
        self._control_snapshot = snapshot
        if self._runtime_state is None:
            return
        self._runtime_state.apply_control_state(
            strategy_enabled=snapshot.strategy_enabled,
            kill_switch_active=snapshot.kill_switch_active,
            protection_mode_active=snapshot.protection_mode_active,
        )

    def _market_data_is_fresh(self, as_of: datetime) -> bool:
        if self._latest_final_bar_time is None:
            return False
        threshold = max(
            timeframe_to_timedelta(self._timeframe) * 2,
            timedelta(seconds=self._market_stale_threshold_seconds),
        )
        return as_of - self._latest_final_bar_time <= threshold

    def _not_ready_reason(self) -> str:
        if self._runtime_state is None:
            return "runtime_unbound"
        as_of = self._clock()
        if self._lease_snapshot.fencing_token is None:
            return "lease_not_acquired"
        if not self._lease_snapshot.is_held_by(
            instance_id=self._runtime_state.instance_id,
            as_of=as_of,
        ):
            return "lease_lost_or_expired"
        if self._latest_final_bar_time is None:
            return "latest_final_bar_missing"
        if self._current_trading_phase is None:
            return "market_state_missing"
        if not self._market_data_is_fresh(as_of):
            return "market_data_stale"
        return "runtime_not_ready"

    def _track_runtime_safety(
        self,
        *,
        as_of: datetime,
        ready: bool,
        readiness_reason: str | None,
        refresh_reason: str,
    ) -> None:
        if ready:
            self._not_ready_since = None
            self._not_ready_alert_emitted = False
            self._market_stale_cycles = 0
            return

        if self._not_ready_since is None:
            self._not_ready_since = as_of

        if readiness_reason == "market_data_stale":
            self._market_stale_cycles += 1
            if self._market_stale_cycles >= 2:
                self._emit(
                    event_name="runtime.market_data_stale_repeated",
                    severity="warning",
                    message="Market data has remained stale across repeated readiness checks.",
                    notify=True,
                    reason_code="MARKET_DATA_STALE",
                    details={
                        "stale_check_count": self._market_stale_cycles,
                        "refresh_reason": refresh_reason,
                        "latest_final_bar_time": self._latest_final_bar_time,
                    },
                )
        else:
            self._market_stale_cycles = 0

        if (
            not self._not_ready_alert_emitted
            and self._not_ready_since is not None
            and as_of - self._not_ready_since >= timedelta(seconds=30)
        ):
            self._emit(
                event_name="runtime.not_ready_persisted",
                severity="error",
                message="Trader has remained not-ready for more than 30 seconds.",
                notify=True,
                reason_code=(readiness_reason or "NOT_READY").upper(),
                details={
                    "not_ready_since": self._not_ready_since,
                    "refresh_reason": refresh_reason,
                },
            )
            self._not_ready_alert_emitted = True

    def _emit(
        self,
        *,
        event_name: str,
        severity: str,
        message: str,
        notify: bool = False,
        bypass_cooldown: bool = False,
        reason_code: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        runtime_state = self._runtime_state
        self._observability.emit(
            event_name=event_name,
            severity=severity,
            message=message,
            notify=notify,
            bypass_cooldown=bypass_cooldown,
            trader_run_id=runtime_state.trader_run_id if runtime_state is not None else None,
            instance_id=runtime_state.instance_id if runtime_state is not None else None,
            account_id=self._account_id,
            control_state=(
                runtime_state.control_state.value
                if runtime_state is not None
                else self._control_snapshot.control_state.value
            ),
            reason_code=reason_code,
            fencing_token=self._lease_snapshot.fencing_token,
            details=details,
        )

    async def _persist_runtime_status(self) -> None:
        if self._runtime_state is None:
            return
        self._store.save_runtime_status(
            TraderRuntimeStatusSnapshot(
                account_id=self._account_id,
                trader_run_id=self._runtime_state.trader_run_id,
                instance_id=self._runtime_state.instance_id,
                lifecycle_status=self._runtime_state.status,
                health_status=self._runtime_state.health_status,
                readiness_status=self._runtime_state.readiness_status,
                control_state=self._runtime_state.control_state,
                strategy_enabled=self._runtime_state.strategy_enabled,
                kill_switch_active=self._runtime_state.kill_switch_active,
                protection_mode_active=self._runtime_state.protection_mode_active,
                market_data_fresh=self._runtime_state.market_data_fresh,
                latest_final_bar_time=self._runtime_state.latest_final_bar_time,
                current_trading_phase=self._runtime_state.current_trading_phase,
                last_seen_bars={
                    stream_key: dict(snapshot)
                    for stream_key, snapshot in self._runtime_state.last_seen_bars_by_stream.items()
                },
                last_strategy_bars={
                    stream_key: dict(snapshot)
                    for stream_key, snapshot in (
                        self._runtime_state.last_strategy_bars_by_stream.items()
                    )
                },
                fencing_token=self._lease_snapshot.fencing_token,
                last_status_message=self._last_status_message,
                updated_at=self._clock(),
            )
        )


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _shanghai_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=SHANGHAI_TIMEZONE)
    return value.astimezone(SHANGHAI_TIMEZONE)


def _json_object_mapping(value: Any) -> dict[str, dict[str, object]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, dict[str, object]] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, dict):
            normalized[key] = dict(item)
    return normalized
