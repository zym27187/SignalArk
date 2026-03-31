"""FastAPI scaffold for the SignalArk control plane."""

from __future__ import annotations

from fastapi import FastAPI

from src.config import get_settings
from src.shared.logging import configure_logging


def create_app() -> FastAPI:
    """Create the minimal API scaffold used before Phase 6B is implemented."""
    settings = get_settings()
    configure_logging(settings.log_level)

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
            "status": "scaffold",
        }

    @app.get("/health/live")
    async def health_live() -> dict[str, object]:
        return {
            "status": "alive",
            "service": settings.app_name,
            "note": "Readiness and operator controls are implemented in Phase 6B.",
        }

    return app


app = create_app()

