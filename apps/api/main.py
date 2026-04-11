"""FastAPI scaffold for the SignalArk control plane."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from src.config import get_settings
from src.domain.strategy.ai import AiProviderRequestError
from src.infra.db import create_database_engine, create_session_factory
from src.infra.observability import build_observability
from src.shared.logging import configure_logging

from apps.api.control_plane import ApiControlPlaneService
from apps.trader.control_plane import MissingControlPlaneSchemaError, TraderControlPlaneStore


class ResearchAiSnapshotRequest(BaseModel):
    """Body contract for one AI-driven research snapshot request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)

    symbol: str | None = None
    timeframe: str | None = None
    limit: int = Field(default=96, ge=1, le=500)
    provider: Literal["heuristic_stub", "openai_compatible"] | None = None
    model: str | None = None
    base_url: str | None = Field(default=None, alias="baseUrl")
    api_key: str | None = Field(default=None, alias="apiKey")


class ResearchAiSettingsUpdateRequest(BaseModel):
    """Body contract for persisting AI research settings."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)

    provider: Literal["heuristic_stub", "openai_compatible"]
    model: str
    base_url: str = Field(alias="baseUrl")
    api_key: str | None = Field(default=None, alias="apiKey")
    clear_api_key: bool = Field(default=False, alias="clearApiKey")


class RuntimeSymbolRequest(BaseModel):
    """Body contract for recording one runtime-symbol change request."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    symbol: str
    confirm: bool = False


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
            allow_methods=["GET", "POST", "PUT", "OPTIONS"],
            allow_headers=["*"],
        )

    @app.get("/")
    async def root() -> dict[str, object]:
        return {
            "service": settings.app_name,
            "env": settings.env,
            "execution_mode": settings.execution_mode,
            "symbols": settings.symbols,
            "symbol_names": settings.symbol_names,
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

    @app.get("/v1/contracts/shared")
    async def shared_contracts() -> dict[str, object]:
        return service.shared_contracts_payload()

    @app.get("/v1/symbols/inspect")
    async def inspect_symbol(symbol: str) -> dict[str, object]:
        return service.inspect_symbol_payload(symbol)

    @app.post("/v1/symbols/runtime-requests")
    async def request_runtime_symbol(request: RuntimeSymbolRequest) -> dict[str, object]:
        try:
            return service.request_runtime_symbol(
                symbol=request.symbol,
                confirm=request.confirm,
            )
        except MissingControlPlaneSchemaError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/v1/balance/summary")
    async def balance_summary() -> dict[str, object]:
        return service.balance_summary_payload()

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

    @app.get("/v1/market/runtime-bars")
    async def market_runtime_bars(
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> dict[str, object]:
        try:
            return service.market_runtime_bars_payload(
                symbol=symbol,
                timeframe=timeframe,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        limit: int | None = Query(default=None, ge=1, le=500),
        mode: Literal["preview", "evaluation"] = Query(default="evaluation"),
        slippage_model: Literal["bar_close_bps", "directional_close_tiered_bps"] = Query(
            default="bar_close_bps"
        ),
    ) -> dict[str, object]:
        try:
            return await service.research_snapshot_payload(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                mode=mode,
                slippage_model=slippage_model,
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

    @app.get("/v1/research/ai-settings")
    async def research_ai_settings() -> dict[str, object]:
        return service.research_ai_settings_payload()

    @app.put("/v1/research/ai-settings")
    async def update_research_ai_settings(
        request: ResearchAiSettingsUpdateRequest,
    ) -> dict[str, object]:
        try:
            return service.save_research_ai_settings(
                provider=request.provider,
                model=request.model,
                base_url=request.base_url,
                api_key=request.api_key,
                replace_api_key="api_key" in request.model_fields_set,
                clear_api_key=request.clear_api_key,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except MissingControlPlaneSchemaError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/v1/research/ai-snapshot")
    async def research_ai_snapshot(request: ResearchAiSnapshotRequest) -> dict[str, object]:
        try:
            return await service.research_ai_snapshot_payload(
                symbol=request.symbol,
                timeframe=request.timeframe,
                limit=request.limit,
                provider=request.provider,
                model=request.model,
                base_url=request.base_url,
                api_key=request.api_key,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except AiProviderRequestError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
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
