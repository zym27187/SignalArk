"""Runtime settings and config loading for SignalArk."""

from __future__ import annotations

import os
from collections.abc import Mapping
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIGS_DIR = ROOT_DIR / "configs"
DOTENV_PATH = ROOT_DIR / ".env"
ENV_PREFIX = "SIGNALARK_"
DEFAULT_CONFIG_PROFILE = "dev"
FIXED_SUPPORTED_SYMBOLS = ("600036.SH", "000001.SZ")
DEFAULT_SYMBOL_RULES = {
    "600036.SH": {
        "lot_size": "100",
        "qty_step": "100",
        "price_tick": "0.01",
        "min_qty": "100",
        "allow_odd_lot_sell": True,
        "t_plus_one_sell": True,
        "price_limit_pct": "0.10",
    },
    "000001.SZ": {
        "lot_size": "100",
        "qty_step": "100",
        "price_tick": "0.01",
        "min_qty": "100",
        "allow_odd_lot_sell": True,
        "t_plus_one_sell": True,
        "price_limit_pct": "0.10",
    },
}
DEFAULT_PAPER_COST_MODEL = {
    "commission": "0.0003",
    "transfer_fee": "0.00001",
    "stamp_duty_sell": "0.0005",
}
DEFAULT_API_CORS_ALLOWED_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:4173",
    "http://localhost:4173",
)
YAML_PATH_TO_FIELD = {
    ("runtime", "config_profile"): "config_profile",
    ("runtime", "shared_config_entrypoint"): "shared_config_entrypoint",
    ("runtime", "trader_run_id_generation"): "trader_run_id_generation",
    ("runtime", "trader_run_id_bind_to_logs"): "trader_run_id_bind_to_logs",
    ("runtime", "trader_run_id_bind_to_audit"): "trader_run_id_bind_to_audit",
    ("app", "name"): "app_name",
    ("app", "env"): "env",
    ("app", "timezone"): "timezone",
    ("trading", "exchange"): "exchange",
    ("trading", "market"): "market",
    ("trading", "execution_mode"): "execution_mode",
    ("trading", "account_id"): "account_id",
    ("trading", "primary_strategy_id"): "primary_strategy_id",
    ("trading", "supported_symbols"): "supported_symbols",
    ("trading", "symbols"): "symbols",
    ("trading", "primary_timeframe"): "primary_timeframe",
    ("trading", "market_data_mode"): "market_data_mode",
    ("trading", "market_data_source"): "market_data_source",
    ("trading", "strategy_trigger"): "strategy_trigger",
    ("trading", "symbol_rules"): "symbol_rules",
    ("paper", "state_backend"): "paper_state_backend",
    ("paper", "cost_model"): "paper_cost_model",
    ("paper", "recovery_source"): "paper_recovery_source",
    ("api", "host"): "api_host",
    ("api", "port"): "api_port",
    ("api", "cors_allowed_origins"): "api_cors_allowed_origins",
    ("logging", "level"): "log_level",
    ("logging", "format"): "log_format",
    ("logging", "include_trader_run_id"): "log_include_trader_run_id",
    ("risk", "max_single_symbol_notional_cny"): "max_single_symbol_notional_cny",
    ("risk", "max_total_open_notional_cny"): "max_total_open_notional_cny",
    ("risk", "min_order_notional_cny"): "min_order_notional_cny",
    ("risk", "market_stale_threshold_seconds"): "market_stale_threshold_seconds",
    ("controls", "lease_ttl_seconds"): "lease_ttl_seconds",
    ("controls", "lease_heartbeat_interval_seconds"): "lease_heartbeat_interval_seconds",
    ("alerts", "telegram", "enabled"): "telegram_enabled",
}


class AshareSymbolRule(BaseModel):
    """Fixed A-share trading rules for one supported symbol."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    lot_size: Decimal = Field(gt=Decimal("0"))
    qty_step: Decimal = Field(gt=Decimal("0"))
    price_tick: Decimal = Field(gt=Decimal("0"))
    min_qty: Decimal = Field(gt=Decimal("0"))
    allow_odd_lot_sell: bool
    t_plus_one_sell: bool
    price_limit_pct: Decimal = Field(gt=Decimal("0"), lt=Decimal("1"))

    @model_validator(mode="after")
    def validate_rule_consistency(self) -> AshareSymbolRule:
        """Keep quantity and tick rules internally consistent."""
        if self.min_qty < self.lot_size:
            raise ValueError("min_qty must be greater than or equal to lot_size.")
        if self.min_qty % self.qty_step != 0:
            raise ValueError("min_qty must be an integer multiple of qty_step.")
        if self.lot_size % self.qty_step != 0:
            raise ValueError("lot_size must be an integer multiple of qty_step.")
        if not self.t_plus_one_sell:
            raise ValueError("V1 A-share symbol rules must enforce t_plus_one_sell.")
        return self


class PaperCostModel(BaseModel):
    """Minimum configurable paper-trading cost model for A-share V1."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    commission: Decimal = Field(ge=Decimal("0"))
    transfer_fee: Decimal = Field(ge=Decimal("0"))
    stamp_duty_sell: Decimal = Field(ge=Decimal("0"))


def _read_yaml_file(path: Path) -> dict[str, Any]:
    """Read a YAML config file and ensure it is a mapping."""
    if not path.exists():
        raise FileNotFoundError(f"Config file does not exist: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise TypeError(f"Config file must contain a mapping at the top level: {path}")
    return dict(data)


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Deep merge nested config mappings."""
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(current, value)
            continue
        merged[key] = value
    return merged


def _flatten_yaml_config(
    data: Mapping[str, Any],
    *,
    source: Path,
    prefix: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Flatten nested YAML sections into Settings keyword arguments."""
    flat: dict[str, Any] = {}
    for key, value in data.items():
        current_path = prefix + (str(key),)
        field_name = YAML_PATH_TO_FIELD.get(current_path)
        if field_name is not None:
            flat[field_name] = value
            continue

        if isinstance(value, Mapping):
            flat.update(_flatten_yaml_config(value, source=source, prefix=current_path))
            continue

        dotted_key = ".".join(current_path)
        raise ValueError(f"Unsupported config key in {source}: {dotted_key}")
    return flat


def _clean_env_value(value: str | None) -> str | None:
    """Normalize env values while respecting env_ignore_empty semantics."""
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _collect_runtime_env() -> dict[str, str]:
    """Collect .env and process env values with process env taking precedence."""
    env_values: dict[str, str] = {}

    if DOTENV_PATH.exists():
        for key, value in dotenv_values(DOTENV_PATH).items():
            if not key or not key.startswith(ENV_PREFIX):
                continue
            normalized = _clean_env_value(value)
            if normalized is not None:
                env_values[key] = normalized

    for key, value in os.environ.items():
        if not key.startswith(ENV_PREFIX):
            continue
        normalized = _clean_env_value(value)
        if normalized is not None:
            env_values[key] = normalized

    return env_values


def _resolve_config_path(raw_path: str) -> Path:
    """Resolve config file paths relative to the repo root when needed."""
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


def _resolve_config_files(config_profile: str, config_file: str | None) -> list[Path]:
    """Resolve the ordered list of YAML files used for runtime config."""
    paths = [CONFIGS_DIR / "base.yaml"]

    if config_profile != "base":
        profile_path = CONFIGS_DIR / f"{config_profile}.yaml"
        if not profile_path.exists():
            raise FileNotFoundError(f"Config profile is not defined: {profile_path}")
        paths.append(profile_path)

    if config_file is not None:
        explicit_path = _resolve_config_path(config_file)
        if not explicit_path.exists():
            raise FileNotFoundError(f"Explicit config file does not exist: {explicit_path}")
        paths.append(explicit_path)

    return paths


class Settings(BaseSettings):
    """Typed runtime settings aligned with the V1 fixed boundaries."""

    model_config = SettingsConfigDict(
        env_prefix="SIGNALARK_",
        env_file=str(ROOT_DIR / ".env"),
        env_ignore_empty=True,
        enable_decoding=False,
        extra="ignore",
        case_sensitive=False,
    )

    config_profile: Literal["dev"] = DEFAULT_CONFIG_PROFILE
    config_file: str | None = None
    shared_config_entrypoint: Literal["src.config.get_settings"] = "src.config.get_settings"
    trader_run_id_generation: Literal["uuid4"] = "uuid4"
    trader_run_id_bind_to_logs: bool = True
    trader_run_id_bind_to_audit: bool = True

    app_name: str = "signalark"
    env: Literal["dev", "test", "prod"] = "dev"
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"

    exchange: Literal["cn_equity"] = "cn_equity"
    market: Literal["a_share"] = "a_share"
    execution_mode: Literal["paper"] = "paper"
    account_id: Literal["paper_account_001"] = "paper_account_001"
    primary_strategy_id: Literal["baseline_momentum_v1", "ai_bar_judge_v1"] = (
        "baseline_momentum_v1"
    )
    supported_symbols: list[str] = Field(default_factory=lambda: list(FIXED_SUPPORTED_SYMBOLS))
    symbols: list[str] = Field(default_factory=lambda: ["600036.SH"])
    primary_timeframe: Literal["15m"] = "15m"
    market_data_mode: Literal["bar"] = "bar"
    market_data_source: Literal["eastmoney"] = "eastmoney"
    strategy_trigger: Literal["closed_bar"] = "closed_bar"
    symbol_rules: dict[str, AshareSymbolRule] = Field(
        default_factory=lambda: {
            symbol: AshareSymbolRule(**rule)
            for symbol, rule in DEFAULT_SYMBOL_RULES.items()
        }
    )

    paper_state_backend: Literal["postgres"] = "postgres"
    paper_cost_model: PaperCostModel = Field(
        default_factory=lambda: PaperCostModel(**DEFAULT_PAPER_COST_MODEL)
    )
    paper_recovery_source: Literal["local_persistent_state"] = "local_persistent_state"

    postgres_dsn: str = "postgresql+psycopg://signalark:signalark@localhost:5432/signalark"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_cors_allowed_origins: list[str] = Field(
        default_factory=lambda: list(DEFAULT_API_CORS_ALLOWED_ORIGINS)
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json"] = "json"
    log_include_trader_run_id: bool = True

    lease_ttl_seconds: int = 15
    lease_heartbeat_interval_seconds: int = 5
    market_stale_threshold_seconds: int = 120

    max_single_symbol_notional_cny: Decimal = Decimal("200000")
    max_total_open_notional_cny: Decimal = Decimal("500000")
    min_order_notional_cny: Decimal = Decimal("1000")

    telegram_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    @field_validator("supported_symbols", "symbols", mode="before")
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

    @field_validator("symbol_rules", mode="before")
    @classmethod
    def normalize_symbol_rule_keys(cls, value: object) -> object:
        """Normalize symbol-rule mapping keys to uppercase symbols."""
        if value is None:
            return value
        if not isinstance(value, Mapping):
            raise TypeError("symbol_rules must be a mapping keyed by symbol.")
        return {str(symbol).strip().upper(): rule for symbol, rule in value.items()}

    @field_validator("api_cors_allowed_origins", mode="before")
    @classmethod
    def normalize_api_cors_allowed_origins(cls, value: object) -> list[str]:
        """Support YAML lists and comma-separated env values for API CORS origins."""
        if value is None:
            return list(DEFAULT_API_CORS_ALLOWED_ORIGINS)

        if isinstance(value, str):
            candidates = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, list):
            candidates = [str(item).strip() for item in value if str(item).strip()]
        else:
            raise TypeError("api_cors_allowed_origins must be a list or a comma-separated string")

        normalized_origins: list[str] = []
        seen_origins: set[str] = set()
        for candidate in candidates:
            normalized = candidate.rstrip("/")
            if not normalized.startswith(("http://", "https://")):
                raise ValueError(
                    "api_cors_allowed_origins entries must include http:// or https:// scheme."
                )
            if normalized in seen_origins:
                continue
            seen_origins.add(normalized)
            normalized_origins.append(normalized)

        return normalized_origins

    @field_validator("config_file", "telegram_bot_token", "telegram_chat_id", mode="before")
    @classmethod
    def normalize_optional_strings(cls, value: object) -> str | None:
        """Treat empty strings as missing for optional string settings."""
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_v1_contracts(self) -> Settings:
        """Enforce the V1 fixed boundaries and fail fast on invalid config."""
        if self.supported_symbols != list(FIXED_SUPPORTED_SYMBOLS):
            raise ValueError("V1 supported_symbols are fixed to 600036.SH and 000001.SZ.")

        if not 1 <= len(self.symbols) <= 3:
            raise ValueError("V1 only supports 1-3 symbols.")

        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("V1 symbols must be unique.")

        if not set(self.symbols).issubset(set(self.supported_symbols)):
            raise ValueError("Runtime symbols must be a subset of the V1 supported_symbols list.")

        if set(self.symbol_rules) != set(self.supported_symbols):
            raise ValueError("A-share symbol_rules must be declared for every supported symbol.")

        if self.execution_mode != "paper":
            raise ValueError("V1 execution_mode must remain paper.")

        if self.market_data_source != "eastmoney":
            raise ValueError("V1 market_data_source must remain eastmoney.")

        if self.lease_heartbeat_interval_seconds >= self.lease_ttl_seconds:
            raise ValueError("Lease heartbeat interval must be smaller than lease TTL.")

        if self.max_single_symbol_notional_cny <= 0:
            raise ValueError("max_single_symbol_notional_cny must be positive.")

        if self.max_total_open_notional_cny <= 0:
            raise ValueError("max_total_open_notional_cny must be positive.")

        if self.min_order_notional_cny <= 0:
            raise ValueError("min_order_notional_cny must be positive.")

        if self.api_port <= 0:
            raise ValueError("api_port must be positive.")

        if not self.postgres_dsn.strip():
            raise ValueError("postgres_dsn must not be empty.")

        has_bot_token = bool(self.telegram_bot_token)
        has_chat_id = bool(self.telegram_chat_id)
        if self.telegram_enabled and not (has_bot_token and has_chat_id):
            raise ValueError(
                "Telegram alerting requires SIGNALARK_TELEGRAM_BOT_TOKEN and "
                "SIGNALARK_TELEGRAM_CHAT_ID when alerts are enabled."
            )
        if has_bot_token != has_chat_id:
            raise ValueError(
                "Telegram alerting requires both SIGNALARK_TELEGRAM_BOT_TOKEN and "
                "SIGNALARK_TELEGRAM_CHAT_ID."
            )

        if self.trader_run_id_bind_to_logs and not self.log_include_trader_run_id:
            raise ValueError("log_include_trader_run_id must stay enabled for V1 auditability.")

        return self


def _field_name_from_env_key(env_key: str) -> str:
    """Translate a SIGNALARK_* env key into a Settings field name."""
    return env_key.removeprefix(ENV_PREFIX).lower()


def _build_env_overrides(env_values: Mapping[str, str]) -> dict[str, str]:
    """Convert runtime env values into Settings kwargs."""
    overrides: dict[str, str] = {}
    for env_key, value in env_values.items():
        field_name = _field_name_from_env_key(env_key)
        if field_name in Settings.model_fields:
            overrides[field_name] = value
    return overrides


def _validate_required_runtime_env(settings: Settings, env_values: Mapping[str, str]) -> None:
    """Validate the required env/secret contract used at runtime startup."""
    missing_env: list[str] = []

    if settings.paper_state_backend == "postgres" and "SIGNALARK_POSTGRES_DSN" not in env_values:
        missing_env.append("SIGNALARK_POSTGRES_DSN")

    if settings.telegram_enabled:
        for env_key in ("SIGNALARK_TELEGRAM_BOT_TOKEN", "SIGNALARK_TELEGRAM_CHAT_ID"):
            if env_key not in env_values:
                missing_env.append(env_key)

    if missing_env:
        formatted = ", ".join(missing_env)
        raise ValueError(
            "Missing required env variables for SignalArk runtime startup: "
            f"{formatted}"
        )


def load_settings(
    *,
    config_profile: str | None = None,
    config_file: str | Path | None = None,
) -> Settings:
    """Load settings from YAML layers first, then override with env values."""
    env_values = _collect_runtime_env()

    resolved_profile = config_profile or env_values.get(
        "SIGNALARK_CONFIG_PROFILE",
        DEFAULT_CONFIG_PROFILE,
    )

    if config_file is None:
        resolved_config_file = env_values.get("SIGNALARK_CONFIG_FILE")
    else:
        resolved_config_file = str(config_file)

    merged_yaml: dict[str, Any] = {}
    for path in _resolve_config_files(resolved_profile, resolved_config_file):
        merged_yaml = _deep_merge(merged_yaml, _read_yaml_file(path))

    yaml_values = _flatten_yaml_config(merged_yaml, source=CONFIGS_DIR)
    merged_values: dict[str, Any] = {
        **yaml_values,
        **_build_env_overrides(env_values),
        "config_profile": resolved_profile,
        "config_file": resolved_config_file,
    }

    settings = Settings(**merged_values)
    _validate_required_runtime_env(settings, env_values)
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the shared process-level settings object for runtime entrypoints."""
    return load_settings()


def clear_settings_cache() -> None:
    """Clear the cached settings instance, mainly for tests and local scripts."""
    get_settings.cache_clear()
