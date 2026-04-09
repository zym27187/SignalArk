"""AI-ready bar-judgment strategy skeleton with a safe fallback provider."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal, Protocol

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.events import BarEvent
from src.domain.strategy.audit import StrategyDecisionAudit
from src.domain.strategy.signal import Signal, SignalType
from src.shared.types import NonEmptyStr, NonNegativeDecimal, UnitIntervalDecimal

AI_BAR_JUDGE_V1 = "ai_bar_judge_v1"
HEURISTIC_STUB = "heuristic_stub"
OPENAI_CHAT_COMPLETIONS = "openai_chat_completions"
ROOT_DIR = Path(__file__).resolve().parents[3]
STRATEGY_CONFIG_DIR = ROOT_DIR / "configs" / "strategies"
PERCENT_DISPLAY_QUANTUM = Decimal("0.0001")
CONFIDENCE_DISPLAY_QUANTUM = Decimal("0.0001")


class AiBarJudgeConfig(BaseModel):
    """Repo-local parameters for the AI-ready bar-judgment strategy."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    strategy_id: str = AI_BAR_JUDGE_V1
    description: str = "LLM-ready bar judgment strategy with a safe heuristic fallback."
    lookback_bars: int = Field(ge=2, le=128)
    target_position: Decimal = Field(gt=Decimal("0"))
    min_confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    provider_mode: Literal["heuristic_stub", "openai_chat_completions"] = HEURISTIC_STUB
    entry_threshold_pct: Decimal = Field(ge=Decimal("0"), lt=Decimal("1"))
    exit_threshold_pct: Decimal = Field(gt=Decimal("-1"), le=Decimal("0"))

    @model_validator(mode="after")
    def validate_thresholds(self) -> AiBarJudgeConfig:
        if self.exit_threshold_pct > self.entry_threshold_pct:
            raise ValueError("exit_threshold_pct cannot exceed entry_threshold_pct")
        return self


class AiStrategyDecision(BaseModel):
    """Structured output expected from a provider-backed AI judgment."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["rebalance", "exit", "hold"]
    confidence: UnitIntervalDecimal
    target_position: NonNegativeDecimal | None = None
    reason_summary: NonEmptyStr
    provider_name: NonEmptyStr = "heuristic_stub"
    diagnostics: dict[str, str] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AiDecisionRequest:
    """Provider-facing snapshot built from the latest finalized bars."""

    strategy_id: str
    symbol: str
    timeframe: str
    received_at: datetime
    recent_bars: tuple[BarEvent, ...]
    target_position: Decimal
    min_confidence: Decimal


class AiDecisionProvider(Protocol):
    """Async provider seam reserved for future LLM or model integrations."""

    async def decide(self, request: AiDecisionRequest) -> AiStrategyDecision: ...


class AiProviderRequestError(RuntimeError):
    """Raised when an external AI provider rejects or malforms a request."""


def _config_path(strategy_id: str) -> Path:
    return STRATEGY_CONFIG_DIR / f"{strategy_id}.yaml"


@lru_cache(maxsize=8)
def load_ai_bar_judge_config(strategy_id: str) -> AiBarJudgeConfig:
    """Load the repo-local AI strategy parameters for one strategy id."""

    normalized_strategy_id = strategy_id.strip()
    path = _config_path(normalized_strategy_id)
    if not path.exists():
        raise FileNotFoundError(f"Strategy config does not exist: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Strategy config must contain a mapping at the top level: {path}")

    config = AiBarJudgeConfig.model_validate(payload)
    if config.strategy_id != normalized_strategy_id:
        raise ValueError(
            "Strategy config id does not match the requested strategy id: "
            f"{config.strategy_id} != {normalized_strategy_id}"
        )
    return config


def _format_pct(ratio: Decimal) -> str:
    return str((ratio * Decimal("100")).quantize(PERCENT_DISPLAY_QUANTUM))


def _format_confidence(value: Decimal) -> str:
    return str(value.quantize(CONFIDENCE_DISPLAY_QUANTUM))


class OpenAiCompatibleDecisionProvider:
    """Call an OpenAI-compatible Chat Completions endpoint and parse JSON output."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        entry_threshold_pct: Decimal,
        exit_threshold_pct: Decimal,
        timeout_seconds: float = 45.0,
        http_client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        normalized_model = model.strip()
        normalized_base_url = base_url.strip().rstrip("/")
        normalized_api_key = api_key.strip()
        if not normalized_model:
            raise ValueError("model is required for OpenAI-compatible AI backtests")
        if not normalized_base_url:
            raise ValueError("base_url is required for OpenAI-compatible AI backtests")
        if not normalized_api_key:
            raise ValueError("api_key is required for OpenAI-compatible AI backtests")

        self._model = normalized_model
        self._base_url = normalized_base_url
        self._api_key = normalized_api_key
        self._entry_threshold_pct = entry_threshold_pct
        self._exit_threshold_pct = exit_threshold_pct
        self._timeout_seconds = timeout_seconds
        self._http_client_factory = http_client_factory or (
            lambda: httpx.AsyncClient(timeout=self._timeout_seconds)
        )

    async def decide(self, request: AiDecisionRequest) -> AiStrategyDecision:
        payload = {
            "model": self._model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an A-share long-only signal judge. "
                        "Return a single JSON object with keys: action, confidence, "
                        "target_position, reason_summary, provider_name, diagnostics. "
                        "Use action=rebalance to move toward the configured target position, "
                        "action=exit to flatten to zero, and action=hold when the signal is "
                        "not strong enough. Do not return markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(request),
                },
            ],
        }
        try:
            async with self._http_client_factory() as client:
                response = await client.post(
                    self._completion_endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise AiProviderRequestError(f"AI provider request failed: {exc}") from exc

        if 400 <= response.status_code < 500:
            detail = self._extract_error_detail(response)
            raise ValueError(detail)
        if response.status_code >= 500:
            detail = self._extract_error_detail(response)
            raise AiProviderRequestError(detail)

        content = self._extract_content(response)
        decision_payload = self._parse_json_object(content)
        if decision_payload.get("provider_name") in (None, ""):
            decision_payload["provider_name"] = "openai_compatible"
        decision = AiStrategyDecision.model_validate(decision_payload)
        if decision.action == "rebalance" and decision.target_position is None:
            return decision.model_copy(update={"target_position": request.target_position})
        if decision.action == "exit" and decision.target_position is None:
            return decision.model_copy(update={"target_position": Decimal("0")})
        if decision.action == "hold":
            return decision.model_copy(update={"target_position": None})
        return decision

    def metadata(self) -> dict[str, str]:
        return {
            "provider_name": "openai_compatible",
            "model": self._model,
            "base_url": self._base_url,
        }

    @property
    def _completion_endpoint(self) -> str:
        if self._base_url.endswith("/chat/completions"):
            return self._base_url
        return f"{self._base_url}/chat/completions"

    def _build_prompt(self, request: AiDecisionRequest) -> str:
        recent_bars = [
            {
                "bar_start_time": bar.bar_start_time.isoformat(),
                "bar_end_time": bar.bar_end_time.isoformat(),
                "open": str(bar.open),
                "high": str(bar.high),
                "low": str(bar.low),
                "close": str(bar.close),
                "volume": str(bar.volume),
                "previous_close": (
                    None if bar.market_state is None else str(bar.market_state.previous_close)
                ),
                "trading_phase": (
                    None if bar.market_state is None else bar.market_state.trading_phase.value
                ),
            }
            for bar in request.recent_bars
        ]
        return json.dumps(
            {
                "task": (
                    "Judge whether the latest finalized bar stack justifies a "
                    "long-only rebalance, exit, or hold decision for research "
                    "backtesting."
                ),
                "constraints": {
                    "market": "A-share",
                    "position_mode": "long_only",
                    "min_confidence": _format_confidence(request.min_confidence),
                    "entry_threshold_pct": _format_pct(self._entry_threshold_pct),
                    "exit_threshold_pct": _format_pct(self._exit_threshold_pct),
                    "target_position": str(request.target_position),
                },
                "context": {
                    "strategy_id": request.strategy_id,
                    "symbol": request.symbol,
                    "timeframe": request.timeframe,
                    "received_at": request.received_at.isoformat(),
                },
                "recent_bars": recent_bars,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _extract_content(response: httpx.Response) -> str:
        payload = response.json()
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AiProviderRequestError("AI provider response did not include choices")
        message = choices[0].get("message")
        if not isinstance(message, Mapping):
            raise AiProviderRequestError("AI provider response did not include a message payload")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise AiProviderRequestError("AI provider response content was empty")
        return content

    @staticmethod
    def _parse_json_object(content: str) -> dict[str, object]:
        raw = content.strip()
        if raw.startswith("```"):
            lines = [line for line in raw.splitlines() if not line.strip().startswith("```")]
            raw = "\n".join(lines).strip()
        if not raw.startswith("{"):
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise AiProviderRequestError("AI provider content did not contain a JSON object")
            raw = raw[start : end + 1]

        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise AiProviderRequestError("AI provider JSON payload must be an object")
        return payload

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        default_detail = f"AI provider request failed with status {response.status_code}."
        try:
            payload = response.json()
        except ValueError:
            raw = response.text.strip()
            return raw or default_detail

        if isinstance(payload, Mapping):
            error_payload = payload.get("error")
            if isinstance(error_payload, Mapping):
                message = error_payload.get("message")
                if isinstance(message, str) and message.strip():
                    return message
            detail = payload.get("detail")
            if isinstance(detail, str) and detail.strip():
                return detail
        return default_detail


class HeuristicStubAiDecisionProvider:
    """Deterministic stand-in provider used until a real model is wired in."""

    def __init__(
        self,
        *,
        entry_threshold_pct: Decimal,
        exit_threshold_pct: Decimal,
    ) -> None:
        self._entry_threshold_pct = entry_threshold_pct
        self._exit_threshold_pct = exit_threshold_pct

    async def decide(self, request: AiDecisionRequest) -> AiStrategyDecision:
        bars = request.recent_bars
        latest_bar = bars[-1]
        first_bar = bars[0]
        previous_bar = bars[-2]
        market_state = latest_bar.market_state
        assert market_state is not None
        latest_momentum = (
            latest_bar.close - market_state.previous_close
        ) / market_state.previous_close
        lookback_return = (latest_bar.close - first_bar.open) / first_bar.open
        short_return = (latest_bar.close - previous_bar.close) / previous_bar.close
        score = max(abs(latest_momentum), abs(lookback_return), abs(short_return))
        confidence = min(Decimal("0.99"), Decimal("0.55") + score * Decimal("100"))
        diagnostics = {
            "lookback_bars": str(len(bars)),
            "latest_momentum_pct": _format_pct(latest_momentum),
            "lookback_return_pct": _format_pct(lookback_return),
            "short_return_pct": _format_pct(short_return),
        }
        if latest_momentum >= self._entry_threshold_pct and lookback_return >= Decimal("0"):
            return AiStrategyDecision(
                action="rebalance",
                confidence=confidence,
                target_position=request.target_position,
                reason_summary=(
                    "heuristic_stub judged the bar stack bullish enough to target the "
                    "configured inventory."
                ),
                provider_name="heuristic_stub",
                diagnostics=diagnostics,
            )
        if latest_momentum <= self._exit_threshold_pct:
            return AiStrategyDecision(
                action="exit",
                confidence=confidence,
                target_position=Decimal("0"),
                reason_summary="heuristic_stub judged downside momentum strong enough to flatten.",
                provider_name="heuristic_stub",
                diagnostics=diagnostics,
            )
        return AiStrategyDecision(
            action="hold",
            confidence=max(Decimal("0.50"), confidence - Decimal("0.05")),
            target_position=None,
            reason_summary="heuristic_stub judged the current bar stack inconclusive.",
            provider_name="heuristic_stub",
            diagnostics=diagnostics,
        )


class AiBarJudgeStrategy:
    """Safe AI-strategy skeleton that can later swap in a real inference provider."""

    def __init__(
        self,
        *,
        account_id: str,
        strategy_id: str = AI_BAR_JUDGE_V1,
        lookback_bars: int = 12,
        target_position: Decimal = Decimal("400"),
        min_confidence: Decimal = Decimal("0.60"),
        provider_mode: Literal["heuristic_stub", "openai_chat_completions"] = HEURISTIC_STUB,
        entry_threshold_pct: Decimal = Decimal("0.0008"),
        exit_threshold_pct: Decimal = Decimal("-0.0005"),
        description: str | None = None,
        provider: AiDecisionProvider | None = None,
        suppress_provider_errors: bool = True,
    ) -> None:
        if lookback_bars < 2:
            raise ValueError("lookback_bars must be at least 2")
        if target_position <= 0:
            raise ValueError("target_position must be positive")
        if min_confidence < 0 or min_confidence > 1:
            raise ValueError("min_confidence must be within [0, 1]")

        self._account_id = account_id
        self._strategy_id = strategy_id
        self._lookback_bars = lookback_bars
        self._target_position = target_position
        self._min_confidence = min_confidence
        self._provider_mode = provider_mode
        self._entry_threshold_pct = entry_threshold_pct
        self._exit_threshold_pct = exit_threshold_pct
        self._suppress_provider_errors = suppress_provider_errors
        self._description = (
            description or "LLM-ready bar judgment strategy with a safe heuristic fallback."
        )
        self._provider = provider or HeuristicStubAiDecisionProvider(
            entry_threshold_pct=entry_threshold_pct,
            exit_threshold_pct=exit_threshold_pct,
        )
        self._history: dict[str, deque[BarEvent]] = defaultdict(
            lambda: deque(maxlen=self._lookback_bars)
        )
        self._latest_audit: dict[str, StrategyDecisionAudit] = {}

    async def on_bar(self, event: BarEvent, context: object) -> Signal | None:
        if not event.actionable or event.market_state is None:
            return None
        if event.market_state.previous_close <= 0:
            return None

        history = self._history[event.symbol]
        history.append(event)
        if len(history) < self._lookback_bars:
            return None

        request = AiDecisionRequest(
            strategy_id=self._strategy_id,
            symbol=event.symbol,
            timeframe=event.timeframe,
            received_at=self._resolve_received_at(context, fallback=event.ingest_time),
            recent_bars=tuple(history),
            target_position=self._target_position,
            min_confidence=self._min_confidence,
        )
        try:
            decision = await self._provider.decide(request)
        except Exception:
            if not self._suppress_provider_errors:
                raise
            return None

        if decision.action == "hold" or decision.confidence < self._min_confidence:
            return None

        signal_type = SignalType.REBALANCE
        resolved_target_position = self._target_position
        if decision.action == "exit":
            signal_type = SignalType.EXIT
            resolved_target_position = Decimal("0")
        elif decision.target_position is not None and decision.target_position > 0:
            resolved_target_position = decision.target_position

        created_at = max(request.received_at, event.event_time)
        signal = Signal(
            strategy_id=self._strategy_id,
            trader_run_id=self._resolve_trader_run_uuid(context),
            account_id=self._account_id,
            exchange=event.exchange,
            symbol=event.symbol,
            timeframe=event.timeframe,
            signal_type=signal_type,
            target_position=resolved_target_position,
            confidence=decision.confidence,
            event_time=event.event_time,
            created_at=created_at,
            reason_summary=decision.reason_summary,
        )
        self._latest_audit[event.bar_key] = self._build_audit_from_decision(
            event=event,
            signal=signal,
            decision=decision,
            history=request.recent_bars,
        )
        return signal

    def build_decision_audit(self, event: BarEvent, signal: Signal) -> StrategyDecisionAudit:
        """Expose the latest structured audit snapshot for one emitted signal."""

        audit = self._latest_audit.get(event.bar_key)
        if audit is not None:
            return audit

        return StrategyDecisionAudit(
            input_snapshot={
                "strategy_description": self._description,
                "provider_mode": self._provider_mode,
                "lookback_bars": str(self._lookback_bars),
                "bar_key": event.bar_key,
                "source_kind": event.source_kind,
                "bar_start_time": event.bar_start_time.isoformat(),
                "bar_end_time": event.bar_end_time.isoformat(),
                "close": str(event.close),
                "previous_close": (
                    None
                    if event.market_state is None
                    else str(event.market_state.previous_close)
                ),
            },
            signal_snapshot={
                "signal_id": str(signal.id),
                "signal_type": signal.signal_type.value,
                "target_position": str(signal.target_position),
                "event_time": signal.event_time.isoformat(),
                "created_at": signal.created_at.isoformat(),
                "confidence": (
                    None if signal.confidence is None else _format_confidence(signal.confidence)
                )
                or "",
            },
            reason_summary=signal.reason_summary or "",
        )

    def backtest_metadata(self) -> dict[str, object]:
        """Expose reproducible metadata for research and backtest manifests."""

        provider_parameters: dict[str, str] = {}
        provider_metadata = getattr(self._provider, "metadata", None)
        if callable(provider_metadata):
            raw_payload = provider_metadata()
            if isinstance(raw_payload, Mapping):
                provider_parameters = {
                    f"provider_{key}": str(value) for key, value in raw_payload.items()
                }

        return {
            "strategy_id": self._strategy_id,
            "description": self._description,
            "parameters": {
                "lookback_bars": self._lookback_bars,
                "target_position": str(self._target_position),
                "min_confidence": _format_confidence(self._min_confidence),
                "provider_mode": self._provider_mode,
                "entry_threshold_pct": _format_pct(self._entry_threshold_pct),
                "exit_threshold_pct": _format_pct(self._exit_threshold_pct),
                **provider_parameters,
            },
        }

    def _build_audit_from_decision(
        self,
        *,
        event: BarEvent,
        signal: Signal,
        decision: AiStrategyDecision,
        history: tuple[BarEvent, ...],
    ) -> StrategyDecisionAudit:
        latest_bar = history[-1]
        first_bar = history[0]
        previous_bar = history[-2]
        assert latest_bar.market_state is not None
        latest_momentum = (
            latest_bar.close - latest_bar.market_state.previous_close
        ) / latest_bar.market_state.previous_close
        lookback_return = (latest_bar.close - first_bar.open) / first_bar.open
        short_return = (latest_bar.close - previous_bar.close) / previous_bar.close
        input_snapshot = {
            "strategy_description": self._description,
            "provider_mode": self._provider_mode,
            "provider_name": decision.provider_name,
            "lookback_bars": str(len(history)),
            "bar_key": event.bar_key,
            "source_kind": event.source_kind,
            "bar_start_time": event.bar_start_time.isoformat(),
            "bar_end_time": event.bar_end_time.isoformat(),
            "close": str(event.close),
            "previous_close": str(latest_bar.market_state.previous_close),
            "latest_momentum_pct": _format_pct(latest_momentum),
            "lookback_return_pct": _format_pct(lookback_return),
            "short_return_pct": _format_pct(short_return),
            "min_confidence": _format_confidence(self._min_confidence),
        }
        for key, value in decision.diagnostics.items():
            input_snapshot[f"diagnostic_{key}"] = value

        signal_snapshot = {
            "signal_id": str(signal.id),
            "signal_type": signal.signal_type.value,
            "target_position": str(signal.target_position),
            "event_time": signal.event_time.isoformat(),
            "created_at": signal.created_at.isoformat(),
            "confidence": (
                "" if signal.confidence is None else _format_confidence(signal.confidence)
            ),
        }
        return StrategyDecisionAudit(
            input_snapshot=input_snapshot,
            signal_snapshot=signal_snapshot,
            reason_summary=decision.reason_summary,
        )

    @staticmethod
    def _resolve_trader_run_uuid(context: object):
        trader_run_uuid = getattr(context, "trader_run_uuid", None)
        if trader_run_uuid is None:
            raise ValueError("strategy context must expose trader_run_uuid")
        return trader_run_uuid

    @staticmethod
    def _resolve_received_at(context: object, *, fallback: datetime) -> datetime:
        received_at = getattr(context, "received_at", None)
        if received_at is None:
            return fallback
        return received_at


def build_ai_bar_judge_strategy(
    *,
    strategy_id: str,
    account_id: str,
    provider_factory: Callable[[AiBarJudgeConfig], AiDecisionProvider] | None = None,
) -> AiBarJudgeStrategy:
    """Resolve the repo-local config into a runtime AI strategy implementation."""

    config = load_ai_bar_judge_config(strategy_id)
    provider = None if provider_factory is None else provider_factory(config)
    return AiBarJudgeStrategy(
        account_id=account_id,
        strategy_id=config.strategy_id,
        lookback_bars=config.lookback_bars,
        target_position=config.target_position,
        min_confidence=config.min_confidence,
        provider_mode=config.provider_mode,
        entry_threshold_pct=config.entry_threshold_pct,
        exit_threshold_pct=config.exit_threshold_pct,
        description=config.description,
        provider=provider,
    )
