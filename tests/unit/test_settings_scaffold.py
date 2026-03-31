from __future__ import annotations

import pytest

from src.config.settings import Settings


def test_settings_parse_symbols_from_csv() -> None:
    settings = Settings(symbols="btcusdt, ethusdt")

    assert settings.symbols == ["BTCUSDT", "ETHUSDT"]


def test_execution_mode_is_paper_only() -> None:
    with pytest.raises(ValueError, match="paper"):
        Settings(execution_mode="live")


def test_lease_heartbeat_must_be_shorter_than_ttl() -> None:
    with pytest.raises(ValueError, match="smaller than lease TTL"):
        Settings(lease_ttl_seconds=10, lease_heartbeat_interval_seconds=10)
