"""Shared strategy decision-audit contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StrategyDecisionAudit:
    """Structured audit data for one strategy decision."""

    input_snapshot: dict[str, str | None]
    signal_snapshot: dict[str, str]
    reason_summary: str
