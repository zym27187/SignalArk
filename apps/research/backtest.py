"""Thin research runner that wires settings into the Phase 8 backtest service."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from src.config import Settings
from src.domain.events import BarEvent
from src.domain.strategy import build_strategy
from src.services.backtest import BacktestRunResult, BacktestService
from src.services.backtest.service import BacktestStrategyPort


class ResearchBacktestRunner:
    """Build a reusable research-time backtest from repo-local settings."""

    def __init__(
        self,
        settings: Settings,
        *,
        strategy: BacktestStrategyPort | None = None,
        initial_cash: Decimal = Decimal("100000"),
        slippage_bps: Decimal = Decimal("5"),
        slippage_model: str = "bar_close_bps",
    ) -> None:
        self._settings = settings
        self._strategy = strategy or build_strategy(
            strategy_id=settings.primary_strategy_id,
            account_id=settings.account_id,
        )
        self._service = BacktestService(
            account_id=settings.account_id,
            strategy=self._strategy,
            symbol_rules=settings.symbol_rules,
            cost_model=settings.paper_cost_model,
            initial_cash=initial_cash,
            slippage_bps=slippage_bps,
            slippage_model=slippage_model,
        )

    @property
    def strategy(self) -> BacktestStrategyPort:
        """Expose the resolved strategy, including any explicit injected override."""
        return self._strategy

    async def run(self, bars: Iterable[BarEvent]) -> BacktestRunResult:
        """Execute one minimal replay against finalized bar events."""
        return await self._service.run(bars)


def build_default_backtest_runner(
    settings: Settings,
    *,
    strategy: BacktestStrategyPort | None = None,
    initial_cash: Decimal = Decimal("100000"),
    slippage_bps: Decimal = Decimal("5"),
    slippage_model: str = "bar_close_bps",
) -> ResearchBacktestRunner:
    """Mirror trader wiring while allowing research-time strategy overrides."""
    return ResearchBacktestRunner(
        settings,
        strategy=strategy,
        initial_cash=initial_cash,
        slippage_bps=slippage_bps,
        slippage_model=slippage_model,
    )
