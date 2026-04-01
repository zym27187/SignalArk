"""Market-data adapters land here in Phase 3 and Phase 5B."""

from src.infra.exchanges.eastmoney import EastmoneyAshareBarGateway, EastmoneyAshareBarNormalizer
from src.infra.exchanges.paper import (
    PaperExecutionAdapter,
    PaperExecutionScenario,
    PaperFillSlice,
    PaperScenarioResolver,
)

__all__ = [
    "EastmoneyAshareBarGateway",
    "EastmoneyAshareBarNormalizer",
    "PaperExecutionAdapter",
    "PaperExecutionScenario",
    "PaperFillSlice",
    "PaperScenarioResolver",
]
