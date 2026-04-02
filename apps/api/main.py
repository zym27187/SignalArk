"""FastAPI scaffold for the SignalArk control plane."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
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
    if settings.api_cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.api_cors_allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
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

    @app.get("/v1/orders/history")
    async def order_history(
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        trader_run_id: UUID | None = None,
        account_id: str | None = None,
        symbol: str | None = None,
        status: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, object]:
        return service.order_history_payload(
            start_time=start_time,
            end_time=end_time,
            trader_run_id=trader_run_id,
            account_id=account_id,
            symbol=symbol,
            status=status,
            limit=limit,
        )

    @app.get("/v1/fills/history")
    async def fill_history(
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        trader_run_id: UUID | None = None,
        account_id: str | None = None,
        symbol: str | None = None,
        order_id: UUID | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, object]:
        return service.fill_history_payload(
            start_time=start_time,
            end_time=end_time,
            trader_run_id=trader_run_id,
            account_id=account_id,
            symbol=symbol,
            order_id=order_id,
            limit=limit,
        )

    @app.get("/v1/market/bars")
    async def market_bars(
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: int = Query(default=96, ge=1, le=500),
    ) -> dict[str, object]:
        try:
            return await service.market_bars_payload(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=503,
                detail="Market data is temporarily unavailable.",
            ) from exc

    @app.get("/v1/portfolio/equity-curve")
    async def equity_curve(
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: int = Query(default=96, ge=1, le=500),
    ) -> dict[str, object]:
        try:
            return await service.equity_curve_payload(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=503,
                detail="Market data is temporarily unavailable.",
            ) from exc

    @app.get("/v1/research/snapshot")
    async def research_snapshot(
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: int = Query(default=96, ge=1, le=500),
    ) -> dict[str, object]:
        try:
            return await service.research_snapshot_payload(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=503,
                detail="Market data is temporarily unavailable.",
            ) from exc

    @app.get("/v1/diagnostics/replay-events")
    async def replay_events(
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        trader_run_id: UUID | None = None,
        account_id: str | None = None,
        symbol: str | None = None,
        limit: int = Query(default=200, ge=1, le=1000),
    ) -> dict[str, object]:
        return service.replay_events_payload(
            start_time=start_time,
            end_time=end_time,
            trader_run_id=trader_run_id,
            account_id=account_id,
            symbol=symbol,
            limit=limit,
        )

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


def app() -> FastAPI:
    """Uvicorn factory entrypoint for the API runtime."""
    return create_app()
