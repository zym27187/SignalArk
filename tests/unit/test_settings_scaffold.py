from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal

import pytest
import src.config.settings as settings_module
from src.config.settings import Settings, clear_settings_cache, get_settings, load_settings


def _clear_signalark_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("SIGNALARK_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def reset_settings_cache() -> Iterator[None]:
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_settings_parse_symbols_from_csv() -> None:
    settings = Settings(symbols="600036.sh, 000001.sz")

    assert settings.symbols == ["600036.SH", "000001.SZ"]


def test_settings_parse_api_cors_origins_from_csv() -> None:
    settings = Settings(
        api_cors_allowed_origins="http://127.0.0.1:5173, http://localhost:4173/"
    )

    assert settings.api_cors_allowed_origins == [
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ]


def test_execution_mode_is_paper_only() -> None:
    with pytest.raises(ValueError, match="paper"):
        Settings(execution_mode="live")


def test_fixture_market_data_source_is_allowed() -> None:
    settings = Settings(market_data_source="fixture")

    assert settings.market_data_source == "fixture"


def test_lease_heartbeat_must_be_shorter_than_ttl() -> None:
    with pytest.raises(ValueError, match="smaller than lease TTL"):
        Settings(lease_ttl_seconds=10, lease_heartbeat_interval_seconds=10)


def test_load_settings_applies_yaml_dotenv_and_process_env_precedence(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_signalark_env(monkeypatch)

    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(
            [
                "SIGNALARK_POSTGRES_DSN=postgresql+psycopg://dotenv:dotenv@localhost:5432/signalark",
                "SIGNALARK_SYMBOLS=000001.sz",
                "SIGNALARK_LOG_LEVEL=WARNING",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "DOTENV_PATH", dotenv_path)
    monkeypatch.setenv("SIGNALARK_API_PORT", "9100")

    settings = load_settings()

    assert settings.config_profile == "dev"
    assert settings.exchange == "cn_equity"
    assert settings.timezone == "Asia/Shanghai"
    assert settings.symbols == ["000001.SZ"]
    assert settings.market_data_source == "eastmoney"
    assert settings.log_level == "WARNING"
    assert settings.api_port == 9100
    assert settings.api_cors_allowed_origins == [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ]
    assert settings.postgres_dsn == "postgresql+psycopg://dotenv:dotenv@localhost:5432/signalark"
    assert settings.symbol_rules["600036.SH"].lot_size == 100
    assert settings.paper_cost_model.stamp_duty_sell == Decimal("0.0005")


def test_load_settings_does_not_reparse_env_file_via_basesettings(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_signalark_env(monkeypatch)

    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(
            [
                "SIGNALARK_POSTGRES_DSN=postgresql+psycopg://postgres:secret@db.example:5432/postgres",
                "SIGNALARK_SYMBOLS=600036.SH,000001.SZ",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "DOTENV_PATH", dotenv_path)
    monkeypatch.setitem(settings_module.Settings.model_config, "env_file", str(dotenv_path))

    settings = load_settings()

    assert settings.postgres_dsn == "postgresql+psycopg://postgres:secret@db.example:5432/postgres"
    assert settings.symbols == ["600036.SH", "000001.SZ"]


def test_get_settings_returns_cached_settings_until_cache_is_cleared(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_signalark_env(monkeypatch)

    monkeypatch.setattr(settings_module, "DOTENV_PATH", tmp_path / ".env")
    monkeypatch.setenv(
        "SIGNALARK_POSTGRES_DSN",
        "postgresql+psycopg://signalark:signalark@localhost:5432/signalark",
    )
    monkeypatch.setenv("SIGNALARK_API_PORT", "8100")

    cached = get_settings()

    monkeypatch.setenv("SIGNALARK_API_PORT", "8200")

    assert get_settings() is cached
    assert get_settings().api_port == 8100

    clear_settings_cache()

    refreshed = get_settings()

    assert refreshed is not cached
    assert refreshed.api_port == 8200
