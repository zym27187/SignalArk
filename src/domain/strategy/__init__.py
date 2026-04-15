"""Strategy contracts, implementations, and signal models."""

from src.domain.strategy.ai import (
    AI_BAR_JUDGE_V1,
    AiBarJudgeConfig,
    AiBarJudgeStrategy,
    build_ai_bar_judge_strategy,
    load_ai_bar_judge_config,
)
from src.domain.strategy.audit import StrategyDecisionAudit
from src.domain.strategy.baseline import (
    BASELINE_MOMENTUM_V1,
    BaselineMomentumConfig,
    BaselineMomentumStrategy,
    build_strategy,
    load_baseline_momentum_config,
)
from src.domain.strategy.rule_based import (
    MOVING_AVERAGE_BAND_V1,
    MovingAverageBandStrategy,
)
from src.domain.strategy.signal import Signal, SignalStatus, SignalType

__all__ = [
    "AI_BAR_JUDGE_V1",
    "BASELINE_MOMENTUM_V1",
    "MOVING_AVERAGE_BAND_V1",
    "AiBarJudgeStrategy",
    "AiBarJudgeConfig",
    "BaselineMomentumStrategy",
    "BaselineMomentumConfig",
    "MovingAverageBandStrategy",
    "Signal",
    "SignalStatus",
    "SignalType",
    "StrategyDecisionAudit",
    "build_ai_bar_judge_strategy",
    "build_strategy",
    "load_ai_bar_judge_config",
    "load_baseline_momentum_config",
]
