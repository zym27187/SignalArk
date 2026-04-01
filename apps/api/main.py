"""FastAPI scaffold for the SignalArk control plane."""

from __future__ import annotations

from fastapi import FastAPI
from src.config import get_settings
from src.infra.db import create_database_engine, create_session_factory
from src.infra.observability import build_observability
from src.shared.logging import configure_logging

from apps.api.control_plane import ApiControlPlaneService
from apps.trader.control_plane import TraderControlPlaneStore


def build_control_plane_service(settings) -> ApiControlPlaneService:
    """Create the shared DB-backed control-plane service."""
    engine = create_database_engine(settings=settings)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory)
    observability = build_observability(
        settings=settings,
        service="api",
        logger_name="signalark.api.control_plane",
    )
    return ApiControlPlaneService(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        observability=observability,
    )


def create_app(
    *,
    settings=None,
    control_plane_service: ApiControlPlaneService | None = None,
) -> FastAPI:
    """Create the minimal control-plane API for SignalArk V1."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, service="api")
    service = control_plane_service or build_control_plane_service(settings)

    app = FastAPI(
        title="SignalArk API",
        version="0.1.0",
        summary="Minimal control-plane scaffold for SignalArk V1.",
    )

    @app.get("/")
    async def root() -> dict[str, object]:
        return {
            "service": settings.app_name,
            "env": settings.env,
            "execution_mode": settings.execution_mode,
            "symbols": settings.symbols,
            "status": "control_plane_ready",
        }

    @app.get("/health/live")
    async def health_live() -> dict[str, object]:
        return service.live_payload()

    @app.get("/health/ready")
    async def health_ready() -> dict[str, object]:
        return service.ready_payload()

    @app.get("/v1/status")
    async def status() -> dict[str, object]:
        return service.status_payload()

    @app.get("/v1/positions")
    async def positions() -> dict[str, object]:
        return service.positions_payload()

    @app.get("/v1/orders/active")
    async def active_orders() -> dict[str, object]:
        return service.active_orders_payload()

    @app.post("/v1/controls/strategy/pause")
    async def strategy_pause() -> dict[str, object]:
        return await service.pause_strategy()

    @app.post("/v1/controls/strategy/resume")
    async def strategy_resume() -> dict[str, object]:
        return await service.resume_strategy()

    @app.post("/v1/controls/kill-switch/enable")
    async def kill_switch_enable() -> dict[str, object]:
        return await service.enable_kill_switch()

    @app.post("/v1/controls/kill-switch/disable")
    async def kill_switch_disable() -> dict[str, object]:
        return await service.disable_kill_switch()

    @app.post("/v1/controls/cancel-all")
    async def cancel_all() -> dict[str, object]:
        return await service.cancel_all()

    return app


app = create_app()
