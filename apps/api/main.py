"""FastAPI scaffold for the SignalArk control plane."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from src.config import get_settings
from src.domain.strategy.ai import AiProviderRequestError
from src.infra.db import create_database_engine, create_session_factory
from src.infra.observability import build_observability
from src.shared.logging import configure_logging

from apps.api.control_plane import ApiControlPlaneService
from apps.research.analysis import ResearchMode
from apps.trader.control_plane import MissingControlPlaneSchemaError, TraderControlPlaneStore

# Freeze the first configurable-rule MVP contract in one place so the API
# boundary stays explicit before the route is wired in.
ResearchRuleTemplate = Literal["moving_average_band_v1"]
RULE_RESEARCH_TEMPLATE_MOVING_AVERAGE_BAND_V1: ResearchRuleTemplate = "moving_average_band_v1"
RULE_RESEARCH_REQUIRED_TIMEFRAME = "1d"
RULE_RESEARCH_REQUEST_BODY = Body(...)


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


class MovingAverageBandRuleConfigRequest(BaseModel):
    """Config block for the first configurable-rule MVP."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)

    ma_window: int = Field(alias="maWindow")
    buy_below_ma_pct: Decimal = Field(alias="buyBelowMaPct")
    sell_above_ma_pct: Decimal = Field(alias="sellAboveMaPct")
    target_position: int = Field(alias="targetPosition")

    @model_validator(mode="after")
    def validate_contract(self) -> MovingAverageBandRuleConfigRequest:
        if self.ma_window < 2:
            raise ValueError("ruleConfig.maWindow must be at least 2.")
        if self.buy_below_ma_pct < 0 or self.buy_below_ma_pct >= 1:
            raise ValueError("ruleConfig.buyBelowMaPct must be within [0, 1).")
        if self.sell_above_ma_pct < 0 or self.sell_above_ma_pct >= 1:
            raise ValueError("ruleConfig.sellAboveMaPct must be within [0, 1).")
        if self.target_position <= 0:
            raise ValueError("ruleConfig.targetPosition must be greater than 0.")
        return self


class ResearchRuleSnapshotRequest(BaseModel):
    """Body contract for one configurable rule-based research snapshot request."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)

    symbol: str | None = None
    timeframe: str = RULE_RESEARCH_REQUIRED_TIMEFRAME
    limit: int = 750
    initial_cash: Decimal = Field(default=Decimal("100000"), alias="initialCash")
    slippage_bps: Decimal = Field(default=Decimal("5"), alias="slippageBps")
    rule_template: ResearchRuleTemplate = Field(alias="ruleTemplate")
    rule_config: MovingAverageBandRuleConfigRequest = Field(alias="ruleConfig")

    @model_validator(mode="after")
    def validate_contract(self) -> ResearchRuleSnapshotRequest:
        if not self.timeframe.strip():
            raise ValueError("timeframe cannot be empty.")
        if self.timeframe.strip().lower() != RULE_RESEARCH_REQUIRED_TIMEFRAME:
            raise ValueError("timeframe must be 1d for moving_average_band_v1.")
        if self.rule_template != RULE_RESEARCH_TEMPLATE_MOVING_AVERAGE_BAND_V1:
            raise ValueError("ruleTemplate must be moving_average_band_v1.")
        if self.initial_cash <= 0:
            raise ValueError("initialCash must be greater than 0.")
        if self.slippage_bps < 0:
            raise ValueError("slippageBps cannot be negative.")
        if self.limit <= 0:
            raise ValueError("limit must be greater than 0.")
        if self.limit <= self.rule_config.ma_window:
            raise ValueError("limit must be greater than ruleConfig.maWindow.")
        return self


class RuntimeSymbolRequest(BaseModel):
    """Body contract for recording one runtime-symbol change request."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    symbol: str
    confirm: bool = False


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors(include_url=False):
        location = ".".join(str(part) for part in error.get("loc", ()))
        message = str(error.get("msg", "Invalid request."))
        if location and location not in message:
            parts.append(f"{location}: {message}")
        else:
            parts.append(message)
    return "; ".join(parts) if parts else "Invalid request."


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

    @app.get("/v1/diagnostics/degraded-mode")
    async def degraded_mode() -> dict[str, object]:
        return service.degraded_mode_payload()

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
        mode: Annotated[ResearchMode, Query()] = "evaluation",
        slippage_model: Literal["bar_close_bps", "directional_close_tiered_bps"] = Query(
            default="bar_close_bps"
        ),
    ) -> dict[str, object]:
        # Keep GET /v1/research/snapshot focused on the repo's existing
        # baseline/AI research flows. Configurable rule backtests use a
        # dedicated POST body contract so a "60 day MA" always means 60 1d bars,
        # not 60 bars of whichever research timeframe the UI currently shows.
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

    @app.post("/v1/research/rule-snapshot")
    async def research_rule_snapshot(
        request_body: dict[str, object] = RULE_RESEARCH_REQUEST_BODY,
    ) -> dict[str, object]:
        try:
            request = ResearchRuleSnapshotRequest.model_validate(request_body)
            return await service.research_rule_snapshot_payload(
                symbol=request.symbol,
                timeframe=request.timeframe,
                limit=request.limit,
                initial_cash=request.initial_cash,
                slippage_bps=request.slippage_bps,
                rule_template=request.rule_template,
                ma_window=request.rule_config.ma_window,
                buy_below_ma_pct=request.rule_config.buy_below_ma_pct,
                sell_above_ma_pct=request.rule_config.sell_above_ma_pct,
                target_position=request.rule_config.target_position,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=_format_validation_error(exc)) from exc
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
