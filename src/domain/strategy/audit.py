"""Shared strategy decision-audit contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

DEFAULT_DETERMINISTIC_PROVIDER_ID = "deterministic_policy"
AuditNaming = Literal["snake_case", "camelCase"]


@dataclass(frozen=True, slots=True)
class StrategyDecisionAuditSummary:
    """Minimal cross-plane strategy decision summary for operators and research UIs."""

    provider_id: str
    model_or_policy_version: str
    decision: str
    confidence: str | None
    reason_summary: str
    fallback_used: bool = False
    fallback_reason: str | None = None


@dataclass(frozen=True, slots=True)
class StrategyDecisionAudit:
    """Structured audit data for one strategy decision."""

    input_snapshot: dict[str, str | None]
    signal_snapshot: dict[str, str]
    reason_summary: str
    summary: StrategyDecisionAuditSummary | None = None


def build_strategy_decision_audit_summary(
    *,
    provider_id: str,
    model_or_policy_version: str,
    decision: str,
    confidence: str | Decimal | None,
    reason_summary: str,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
) -> StrategyDecisionAuditSummary:
    """Build one normalized decision summary shared by research and runtime surfaces."""

    resolved_provider_id = _normalize_text(provider_id) or DEFAULT_DETERMINISTIC_PROVIDER_ID
    resolved_version = _normalize_text(model_or_policy_version) or resolved_provider_id
    resolved_decision = (_normalize_text(decision) or "hold").lower()
    resolved_reason_summary = _normalize_text(reason_summary) or "No decision summary provided."
    resolved_fallback_reason = _normalize_optional_text(fallback_reason)
    return StrategyDecisionAuditSummary(
        provider_id=resolved_provider_id,
        model_or_policy_version=resolved_version,
        decision=resolved_decision,
        confidence=_normalize_confidence(confidence),
        reason_summary=resolved_reason_summary,
        fallback_used=bool(fallback_used),
        fallback_reason=resolved_fallback_reason,
    )


def infer_strategy_decision_audit_summary(
    *,
    strategy_id: str,
    input_snapshot: Mapping[str, str | None],
    signal_snapshot: Mapping[str, str] | None,
    reason_summary: str | None,
    fallback_decision: str = "hold",
    fallback_provider_id: str = DEFAULT_DETERMINISTIC_PROVIDER_ID,
    confidence: str | Decimal | None = None,
) -> StrategyDecisionAuditSummary:
    """Recover a normalized summary from existing snapshot fields."""

    resolved_provider_id = (
        _normalize_optional_text(input_snapshot.get("audit_provider_id"))
        or _normalize_optional_text(input_snapshot.get("provider_id"))
        or _normalize_optional_text(input_snapshot.get("provider_name"))
        or fallback_provider_id
    )
    resolved_version = (
        _normalize_optional_text(input_snapshot.get("audit_model_or_policy_version"))
        or _normalize_optional_text(input_snapshot.get("model_or_policy_version"))
        or strategy_id
    )
    resolved_decision = (
        _normalize_optional_text(input_snapshot.get("audit_decision"))
        or _normalize_optional_text(input_snapshot.get("decision_action"))
        or (
            None
            if signal_snapshot is None
            else _normalize_optional_text(signal_snapshot.get("signal_type"))
        )
        or fallback_decision
    )
    resolved_confidence = confidence
    if resolved_confidence is None and signal_snapshot is not None:
        resolved_confidence = signal_snapshot.get("confidence")

    fallback_used_text = _normalize_optional_text(input_snapshot.get("audit_fallback_used"))
    fallback_reason = _normalize_optional_text(input_snapshot.get("audit_fallback_reason"))
    return build_strategy_decision_audit_summary(
        provider_id=resolved_provider_id,
        model_or_policy_version=resolved_version,
        decision=resolved_decision,
        confidence=resolved_confidence,
        reason_summary=_normalize_optional_text(reason_summary) or "",
        fallback_used=fallback_used_text == "true",
        fallback_reason=fallback_reason,
    )


def serialize_strategy_decision_audit_summary(
    summary: StrategyDecisionAuditSummary,
    *,
    naming: AuditNaming = "snake_case",
) -> dict[str, str | bool | None]:
    """Serialize one summary using the naming convention of the target surface."""

    if naming == "camelCase":
        return {
            "providerId": summary.provider_id,
            "modelOrPolicyVersion": summary.model_or_policy_version,
            "decision": summary.decision,
            "confidence": summary.confidence,
            "reasonSummary": summary.reason_summary,
            "fallbackUsed": summary.fallback_used,
            "fallbackReason": summary.fallback_reason,
        }
    return {
        "provider_id": summary.provider_id,
        "model_or_policy_version": summary.model_or_policy_version,
        "decision": summary.decision,
        "confidence": summary.confidence,
        "reason_summary": summary.reason_summary,
        "fallback_used": summary.fallback_used,
        "fallback_reason": summary.fallback_reason,
    }


def _normalize_confidence(value: str | Decimal | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    return _normalize_optional_text(value)


def _normalize_text(value: str | None) -> str:
    return _normalize_optional_text(value) or ""


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
