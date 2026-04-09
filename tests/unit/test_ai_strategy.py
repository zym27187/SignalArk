from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest
from apps.trader.runtime import TraderRuntimeState
from apps.trader.service import TraderEventContext, build_default_trader_service
from src.config import Settings
from src.domain.events import BarEvent
from src.domain.market import MarketStateSnapshot, SuspensionStatus, TradingPhase
from src.domain.strategy import (
    AI_BAR_JUDGE_V1,
    SignalType,
    build_strategy,
    load_ai_bar_judge_config,
)
from src.domain.strategy.ai import (
    AiBarJudgeStrategy,
    AiDecisionRequest,
    AiStrategyDecision,
    OpenAiCompatibleDecisionProvider,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_TIME = datetime(2026, 4, 1, 14, 0, tzinfo=SHANGHAI)
MARKET_STATE = MarketStateSnapshot(
    trade_date=BASE_TIME.date(),
    previous_close=Decimal("39.47"),
    upper_limit_price=Decimal("43.42"),
    lower_limit_price=Decimal("35.52"),
    trading_phase=TradingPhase.CONTINUOUS_AUCTION,
    suspension_status=SuspensionStatus.ACTIVE,
)


def _context(*, received_at: datetime | None = None) -> TraderEventContext:
    runtime_state = TraderRuntimeState(trader_run_id="11111111-1111-4111-8111-111111111111")
    return TraderEventContext(
        trader_run_id=runtime_state.trader_run_id,
        instance_id=runtime_state.instance_id,
        received_at=received_at or BASE_TIME + timedelta(seconds=2),
        runtime_state=runtime_state,
    )


def _bar_event(*, close: Decimal, offset: int) -> BarEvent:
    event_time = BASE_TIME + timedelta(minutes=15 * offset)
    return BarEvent(
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        bar_start_time=event_time - timedelta(minutes=15),
        bar_end_time=event_time,
        event_time=event_time,
        ingest_time=event_time + timedelta(seconds=1),
        open=close - Decimal("0.03"),
        high=close + Decimal("0.02"),
        low=close - Decimal("0.05"),
        close=close,
        volume=Decimal("1000"),
        closed=True,
        final=True,
        source_kind="realtime",
        market_state=MARKET_STATE,
    )


class ScriptedProvider:
    def __init__(self, decisions: list[AiStrategyDecision]) -> None:
        self._decisions = list(decisions)
        self.requests: list[AiDecisionRequest] = []

    async def decide(self, request: AiDecisionRequest) -> AiStrategyDecision:
        self.requests.append(request)
        return self._decisions.pop(0)


@pytest.mark.asyncio
async def test_ai_strategy_waits_for_lookback_warmup() -> None:
    provider = ScriptedProvider(
        [
            AiStrategyDecision(
                action="rebalance",
                confidence=Decimal("0.72"),
                target_position=Decimal("500"),
                reason_summary="bullish bar stack",
                provider_name="scripted_provider",
            )
        ]
    )
    strategy = AiBarJudgeStrategy(
        account_id="paper_account_001",
        lookback_bars=3,
        min_confidence=Decimal("0.60"),
        provider=provider,
    )

    first = await strategy.on_bar(_bar_event(close=Decimal("39.40"), offset=0), _context())
    second = await strategy.on_bar(_bar_event(close=Decimal("39.55"), offset=1), _context())
    third = await strategy.on_bar(_bar_event(close=Decimal("39.68"), offset=2), _context())

    assert first is None
    assert second is None
    assert third is not None
    assert third.signal_type is SignalType.REBALANCE
    assert third.target_position == Decimal("500")
    assert len(provider.requests) == 1
    assert len(provider.requests[0].recent_bars) == 3


@pytest.mark.asyncio
async def test_ai_strategy_skips_low_confidence_decisions() -> None:
    provider = ScriptedProvider(
        [
            AiStrategyDecision(
                action="rebalance",
                confidence=Decimal("0.55"),
                target_position=Decimal("400"),
                reason_summary="too uncertain",
                provider_name="scripted_provider",
            )
        ]
    )
    strategy = AiBarJudgeStrategy(
        account_id="paper_account_001",
        lookback_bars=2,
        min_confidence=Decimal("0.60"),
        provider=provider,
    )

    await strategy.on_bar(_bar_event(close=Decimal("39.52"), offset=0), _context())
    signal = await strategy.on_bar(_bar_event(close=Decimal("39.64"), offset=1), _context())

    assert signal is None
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_ai_strategy_exposes_structured_decision_audit() -> None:
    provider = ScriptedProvider(
        [
            AiStrategyDecision(
                action="exit",
                confidence=Decimal("0.88"),
                target_position=Decimal("0"),
                reason_summary="bearish reversal",
                provider_name="scripted_provider",
                diagnostics={"cluster": "reversal"},
            )
        ]
    )
    strategy = AiBarJudgeStrategy(
        account_id="paper_account_001",
        lookback_bars=2,
        min_confidence=Decimal("0.60"),
        provider=provider,
        provider_mode="heuristic_stub",
    )
    event_one = _bar_event(close=Decimal("39.52"), offset=0)
    event_two = _bar_event(close=Decimal("39.20"), offset=1)
    context = _context(received_at=event_two.ingest_time)

    await strategy.on_bar(event_one, context)
    signal = await strategy.on_bar(event_two, context)

    assert signal is not None
    assert signal.signal_type is SignalType.EXIT
    assert signal.target_position == Decimal("0")
    assert signal.confidence == Decimal("0.88")

    audit = strategy.build_decision_audit(event_two, signal)
    assert audit.input_snapshot["provider_name"] == "scripted_provider"
    assert audit.input_snapshot["diagnostic_cluster"] == "reversal"
    assert audit.signal_snapshot["confidence"] == "0.8800"
    assert audit.reason_summary == "bearish reversal"


@pytest.mark.asyncio
async def test_ai_strategy_can_surface_provider_errors_for_research_runs() -> None:
    class ExplodingProvider:
        async def decide(self, request: AiDecisionRequest) -> AiStrategyDecision:
            del request
            raise ValueError("invalid api key")

    strategy = AiBarJudgeStrategy(
        account_id="paper_account_001",
        lookback_bars=2,
        min_confidence=Decimal("0.60"),
        provider=ExplodingProvider(),
        suppress_provider_errors=False,
    )

    await strategy.on_bar(_bar_event(close=Decimal("39.52"), offset=0), _context())
    with pytest.raises(ValueError, match="invalid api key"):
        await strategy.on_bar(_bar_event(close=Decimal("39.64"), offset=1), _context())


@pytest.mark.asyncio
async def test_openai_compatible_provider_parses_chat_completions_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://openai.test/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer sk-test"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "gpt-5.4"
        assert payload["messages"][0]["role"] == "system"
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action": "rebalance",
                                    "confidence": "0.82",
                                    "target_position": "500",
                                    "reason_summary": "uptrend confirmed",
                                    "provider_name": "openai",
                                    "diagnostics": {"pattern": "trend"},
                                }
                            )
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    provider = OpenAiCompatibleDecisionProvider(
        model="gpt-5.4",
        base_url="https://openai.test/v1",
        api_key="sk-test",
        entry_threshold_pct=Decimal("0.0008"),
        exit_threshold_pct=Decimal("-0.0005"),
        http_client_factory=lambda: httpx.AsyncClient(transport=transport),
    )

    decision = await provider.decide(
        AiDecisionRequest(
            strategy_id=AI_BAR_JUDGE_V1,
            symbol="600036.SH",
            timeframe="15m",
            received_at=BASE_TIME,
            recent_bars=(
                _bar_event(close=Decimal("39.52"), offset=0),
                _bar_event(close=Decimal("39.64"), offset=1),
            ),
            target_position=Decimal("400"),
            min_confidence=Decimal("0.60"),
        )
    )

    assert decision.action == "rebalance"
    assert decision.confidence == Decimal("0.82")
    assert decision.target_position == Decimal("500")
    assert decision.provider_name == "openai"
    assert decision.diagnostics["pattern"] == "trend"


def test_build_strategy_resolves_ai_bar_judge_from_repo_config() -> None:
    config = load_ai_bar_judge_config(AI_BAR_JUDGE_V1)
    strategy = build_strategy(
        strategy_id=AI_BAR_JUDGE_V1,
        account_id="paper_account_001",
    )

    assert isinstance(strategy, AiBarJudgeStrategy)
    assert config.lookback_bars == 12
    assert config.min_confidence == Decimal("0.60")


@pytest.mark.asyncio
async def test_build_default_trader_service_autowires_ai_strategy_pipeline() -> None:
    trader = build_default_trader_service(
        Settings(
            postgres_dsn="sqlite+pysqlite:///:memory:",
            primary_strategy_id=AI_BAR_JUDGE_V1,
        )
    )

    try:
        pipeline = trader.runtime_snapshot()["pipeline"]
        assert pipeline["strategy"]["handler_name"] == "AiBarJudgeStrategy"
        assert pipeline["risk"]["handler_name"] == "OmsSignalRiskRouter"
        assert pipeline["oms"]["handler_name"] == "TraderOmsService"
    finally:
        await trader._source.aclose()
