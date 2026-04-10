from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from apps.api.control_plane import (
    DEFAULT_AI_RESEARCH_PROVIDER_TIMEOUT_SECONDS,
    ApiControlPlaneService,
)
from apps.trader.control_plane import TraderControlPlaneStore
from fastapi.testclient import TestClient
from src.config.settings import Settings
from src.domain.market import MarketStateSnapshot, NormalizedBar, SuspensionStatus, TradingPhase
from src.domain.strategy.ai import AiStrategyDecision, OpenAiCompatibleDecisionProvider
from src.infra.db import create_database_engine, create_session_factory
from tests.support.migrations import upgrade_database

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


class FakeHistoricalBarGateway:
    def __init__(self, bars: list[NormalizedBar]) -> None:
        self._bars = list(bars)

    async def fetch_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_bars: int | None = None,
    ) -> list[NormalizedBar]:
        assert symbol == "600036.SH"
        assert timeframe == "15m"
        del start_time, end_time
        bars = list(self._bars)
        if max_bars is not None:
            bars = bars[-max_bars:]
        return bars

    async def aclose(self) -> None:
        return None


def _database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'api_research.sqlite3'}"


def _settings(database_url: str) -> Settings:
    return Settings(postgres_dsn=database_url)


def _bar(
    *,
    index: int = 0,
    event_time: datetime | None = None,
    close: str,
    previous_close: str,
) -> NormalizedBar:
    resolved_event_time = event_time or (BASE_TIME + timedelta(minutes=15 * index))
    return NormalizedBar(
        exchange="cn_equity",
        symbol="600036.SH",
        timeframe="15m",
        bar_start_time=resolved_event_time - timedelta(minutes=15),
        bar_end_time=resolved_event_time,
        ingest_time=resolved_event_time + timedelta(seconds=2),
        open=previous_close,
        high=max(Decimal(close), Decimal(previous_close)),
        low=min(Decimal(close), Decimal(previous_close)),
        close=close,
        volume="1000",
        quote_volume="395000",
        closed=True,
        final=True,
        source_kind="historical",
        market_state=MARKET_STATE.model_copy(
            update={
                "trade_date": resolved_event_time.date(),
                "previous_close": Decimal(previous_close),
            }
        ),
    )


def test_api_research_snapshot_returns_live_backtest_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv("SIGNALARK_POSTGRES_DSN", database_url)
    from src.config import get_settings

    get_settings.cache_clear()
    from apps.api.main import create_app

    settings = _settings(database_url)
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory)
    service = ApiControlPlaneService(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        market_gateway_factory=lambda: FakeHistoricalBarGateway(
                [
                    _bar(index=0, close="39.48", previous_close="39.47"),
                    _bar(index=1, close="39.49", previous_close="39.47"),
                    _bar(index=2, close="39.50", previous_close="39.47"),
                    _bar(index=3, close="39.52", previous_close="39.47"),
                    _bar(
                        event_time=BASE_TIME + timedelta(days=1, minutes=45),
                        close="39.10",
                        previous_close="39.52",
                    ),
                ]
            ),
        )
    app = create_app(settings=settings, control_plane_service=service)

    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/research/snapshot",
                params={
                    "symbol": "600036.SH",
                    "timeframe": "15m",
                    "limit": 5,
                },
            )
    finally:
        engine.dispose()

    assert response.status_code == 200
    payload = response.json()
    assert payload["sourceLabel"] == "由 research API 生成的真实回测结果"
    assert payload["sourceMode"] == "live"
    assert payload["manifest"]["strategyId"] == "baseline_momentum_v1"
    assert payload["manifest"]["symbols"] == ["600036.SH"]
    assert payload["performance"]["tradeCount"] == 3
    assert payload["performance"]["fillCount"] == 3
    assert len(payload["klineBars"]) == 5
    assert len(payload["equityCurve"]) == 5
    assert "runtimePnlCurve" not in payload
    assert "backtestEquityCurve" not in payload
    assert len(payload["decisions"]) == 5
    assert payload["decisions"][0]["skipReason"] == "baseline_trend_warmup"
    assert payload["decisions"][2]["orderPlanSide"] == "BUY"
    assert payload["decisions"][3]["orderPlanSide"] == "BUY"
    assert payload["decisions"][4]["orderPlanSide"] == "SELL"


def test_api_ai_research_snapshot_returns_live_ai_backtest_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv("SIGNALARK_POSTGRES_DSN", database_url)
    from src.config import get_settings

    get_settings.cache_clear()
    from apps.api.main import create_app

    async def fake_decide(self, request):
        del self, request
        return AiStrategyDecision(
            action="rebalance",
            confidence=Decimal("0.91"),
            target_position=Decimal("400"),
            reason_summary="model confirmed the bullish stack",
            provider_name="openai_compatible",
            diagnostics={"regime": "trend"},
        )

    monkeypatch.setattr(OpenAiCompatibleDecisionProvider, "decide", fake_decide)

    settings = _settings(database_url)
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory)
    service = ApiControlPlaneService(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        market_gateway_factory=lambda: FakeHistoricalBarGateway(
            [
                _bar(
                    index=index,
                    close=str(Decimal("39.47") + Decimal("0.03") * index),
                    previous_close="39.47",
                )
                for index in range(12)
            ]
        ),
    )
    app = create_app(settings=settings, control_plane_service=service)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/research/ai-snapshot",
                json={
                    "symbol": "600036.SH",
                    "timeframe": "15m",
                    "limit": 12,
                    "provider": "openai_compatible",
                    "model": "gpt-5.4",
                    "baseUrl": "https://openai.test/v1",
                    "apiKey": "sk-test",
                },
            )
    finally:
        engine.dispose()

    assert response.status_code == 200
    payload = response.json()
    assert payload["sourceMode"] == "live"
    assert payload["sourceLabel"] == "由 research API 生成的 AI 回测结果"
    assert payload["manifest"]["strategyId"] == "ai_bar_judge_v1"
    assert payload["manifest"]["handlerName"] == "AiBarJudgeStrategy"
    assert payload["performance"]["tradeCount"] == 1
    assert payload["performance"]["fillCount"] == 1
    assert payload["decisions"][-1]["action"] == "REBALANCE"
    assert payload["decisions"][-1]["executionAction"] == "BUY"
    assert payload["decisions"][-1]["reasonSummary"] == "model confirmed the bullish stack"
    assert "OpenAI-compatible" in payload["notes"][0]


def test_api_ai_research_strategy_uses_interactive_provider_timeout(tmp_path: Path) -> None:
    database_url = _database_url(tmp_path)
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory)
    service = ApiControlPlaneService(
        settings=_settings(database_url),
        session_factory=session_factory,
        control_store=control_store,
        market_gateway_factory=lambda: FakeHistoricalBarGateway([]),
    )

    try:
        strategy = service._build_research_ai_strategy(
            provider="openai_compatible",
            model="gpt-5.4",
            base_url="https://openai.test/v1",
            api_key="sk-test",
        )
    finally:
        engine.dispose()

    assert isinstance(strategy._provider, OpenAiCompatibleDecisionProvider)
    assert strategy._provider._timeout_seconds == DEFAULT_AI_RESEARCH_PROVIDER_TIMEOUT_SECONDS


def test_api_ai_research_settings_roundtrip_and_snapshot_can_reuse_saved_api_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_url = _database_url(tmp_path)
    monkeypatch.setenv("SIGNALARK_POSTGRES_DSN", database_url)
    from src.config import get_settings

    get_settings.cache_clear()
    from apps.api.main import create_app

    captured = {}

    async def fake_decide(self, request):
        captured["model"] = getattr(self, "_model", None)
        captured["base_url"] = getattr(self, "_base_url", None)
        captured["api_key"] = getattr(self, "_api_key", None)
        del request
        return AiStrategyDecision(
            action="rebalance",
            confidence=Decimal("0.83"),
            target_position=Decimal("400"),
            reason_summary="saved config triggered the entry",
            provider_name="openai_compatible",
            diagnostics={"source": "saved_settings"},
        )

    monkeypatch.setattr(OpenAiCompatibleDecisionProvider, "decide", fake_decide)

    settings = _settings(database_url)
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory)
    service = ApiControlPlaneService(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        market_gateway_factory=lambda: FakeHistoricalBarGateway(
            [
                _bar(
                    index=index,
                    close=str(Decimal("39.47") + Decimal("0.03") * index),
                    previous_close="39.47",
                )
                for index in range(12)
            ]
        ),
    )
    app = create_app(settings=settings, control_plane_service=service)

    try:
        with TestClient(app) as client:
            initial = client.get("/v1/research/ai-settings")
            assert initial.status_code == 200
            initial_payload = initial.json()
            assert initial_payload["provider"] == "openai_compatible"
            assert initial_payload["model"] == "gpt-5.4"
            assert initial_payload["baseUrl"] == "https://api.openai.com/v1"
            assert initial_payload["hasApiKey"] is False

            saved = client.put(
                "/v1/research/ai-settings",
                json={
                    "provider": "openai_compatible",
                    "model": "gpt-5.4-mini",
                    "baseUrl": "https://saved-provider.test/v1",
                    "apiKey": "sk-saved-secret",
                },
            )
            assert saved.status_code == 200
            saved_payload = saved.json()
            assert saved_payload["provider"] == "openai_compatible"
            assert saved_payload["model"] == "gpt-5.4-mini"
            assert saved_payload["baseUrl"] == "https://saved-provider.test/v1"
            assert saved_payload["hasApiKey"] is True
            assert saved_payload["apiKeyHint"].startswith("sk-")

            reloaded = client.get("/v1/research/ai-settings")
            assert reloaded.status_code == 200
            assert reloaded.json()["hasApiKey"] is True
            assert reloaded.json()["apiKeyHint"] == saved_payload["apiKeyHint"]

            snapshot = client.post(
                "/v1/research/ai-snapshot",
                json={
                    "symbol": "600036.SH",
                    "timeframe": "15m",
                    "limit": 12,
                    "provider": "openai_compatible",
                    "model": "gpt-5.4-mini",
                    "baseUrl": "https://saved-provider.test/v1",
                },
            )
    finally:
        engine.dispose()

    assert snapshot.status_code == 200
    payload = snapshot.json()
    assert payload["manifest"]["strategyId"] == "ai_bar_judge_v1"
    assert payload["decisions"][-1]["action"] == "REBALANCE"
    assert payload["decisions"][-1]["executionAction"] == "BUY"
    assert payload["decisions"][-1]["reasonSummary"] == "saved config triggered the entry"
    assert captured["model"] == "gpt-5.4-mini"
    assert captured["base_url"] == "https://saved-provider.test/v1"
    assert captured["api_key"] == "sk-saved-secret"
