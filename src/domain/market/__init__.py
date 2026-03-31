"""Market-data normalization and gating helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "BarEmissionDecision",
    "BarSourceKind",
    "FinalBarGate",
    "MarketStateSnapshot",
    "NormalizedBar",
    "SuspensionStatus",
    "TradingPhase",
    "build_bar_key",
    "build_bar_stream_key",
    "build_market_state_snapshot",
    "compute_price_limits",
    "derive_a_share_trading_phase",
    "timeframe_to_timedelta",
]

_BARS_EXPORTS = {
    "BarEmissionDecision",
    "BarSourceKind",
    "FinalBarGate",
    "NormalizedBar",
    "build_bar_key",
    "build_bar_stream_key",
    "timeframe_to_timedelta",
}

_STATE_EXPORTS = {
    "MarketStateSnapshot",
    "SuspensionStatus",
    "TradingPhase",
    "build_market_state_snapshot",
    "compute_price_limits",
    "derive_a_share_trading_phase",
}


def __getattr__(name: str) -> object:
    """Lazily expose market helpers without creating import cycles."""
    if name in _BARS_EXPORTS:
        module = import_module("src.domain.market.bars")
        return getattr(module, name)
    if name in _STATE_EXPORTS:
        module = import_module("src.domain.market.state")
        return getattr(module, name)
    raise AttributeError(name)
