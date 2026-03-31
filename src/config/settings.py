"""Minimal runtime settings scaffold for SignalArk."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Typed runtime settings aligned with the V1 fixed boundaries."""

    model_config = SettingsConfigDict(
        env_prefix="SIGNALARK_",
        env_file=str(ROOT_DIR / ".env"),
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "signalark"
    env: Literal["dev", "test", "prod"] = "dev"
    timezone: str = "UTC"

    exchange: Literal["binance"] = "binance"
    market: Literal["spot"] = "spot"
    execution_mode: Literal["paper"] = "paper"
    account_id: str = "paper_account_001"
    primary_strategy_id: str = "baseline_momentum_v1"
    symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    primary_timeframe: Literal["15m", "1h"] = "15m"

    postgres_dsn: str = "postgresql+psycopg://signalark:signalark@localhost:5432/signalark"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    lease_ttl_seconds: int = 15
    lease_heartbeat_interval_seconds: int = 5
    market_stale_threshold_seconds: int = 120

    max_single_symbol_notional_usdt: Decimal = Decimal("5000")
    max_total_open_notional_usdt: Decimal = Decimal("10000")
    min_order_notional_usdt: Decimal = Decimal("25")

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, value: object) -> list[str]:
        """Support comma-separated symbols from env while normalizing case."""
        if isinstance(value, str):
            parts = [item.strip().upper() for item in value.split(",") if item.strip()]
            if not parts:
                raise ValueError("SIGNALARK_SYMBOLS must contain at least one symbol.")
            return parts
        if isinstance(value, list):
            return [str(item).strip().upper() for item in value if str(item).strip()]
        raise TypeError("symbols must be a list or a comma-separated string")

    @model_validator(mode="after")
    def validate_v1_contracts(self) -> "Settings":
        """Enforce the V1 fixed boundaries and fail fast on invalid config."""
        if not 1 <= len(self.symbols) <= 3:
            raise ValueError("V1 only supports 1-3 symbols.")

        if self.execution_mode != "paper":
            raise ValueError("V1 execution_mode must remain paper.")

        if self.lease_heartbeat_interval_seconds >= self.lease_ttl_seconds:
            raise ValueError("Lease heartbeat interval must be smaller than lease TTL.")

        if self.max_single_symbol_notional_usdt <= 0:
            raise ValueError("max_single_symbol_notional_usdt must be positive.")

        if self.max_total_open_notional_usdt <= 0:
            raise ValueError("max_total_open_notional_usdt must be positive.")

        if self.min_order_notional_usdt <= 0:
            raise ValueError("min_order_notional_usdt must be positive.")

        has_bot_token = bool(self.telegram_bot_token)
        has_chat_id = bool(self.telegram_chat_id)
        if has_bot_token != has_chat_id:
            raise ValueError(
                "Telegram alerting requires both SIGNALARK_TELEGRAM_BOT_TOKEN and "
                "SIGNALARK_TELEGRAM_CHAT_ID."
            )

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings object for process-wide reuse."""
    return Settings()

