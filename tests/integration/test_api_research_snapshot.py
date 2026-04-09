from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from apps.api.control_plane import ApiControlPlaneService
from apps.trader.control_plane import TraderControlPlaneStore
from fastapi.testclient import TestClient
from src.config.settings import Settings
from src.domain.market import MarketStateSnapshot, NormalizedBar, SuspensionStatus, TradingPhase
from src.domain.strategy.ai import AiStrategyDecision, OpenAiCompatibleDecisionProvider
from src.infra.db import create_database_engine, create_session_factory

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
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    control_store = TraderControlPlaneStore(session_factory)
    service = ApiControlPlaneService(
        settings=settings,
        session_factory=session_factory,
        control_store=control_store,
        market_gateway_factory=lambda: FakeHistoricalBarGateway(
                [
                    _bar(index=0, close="39.50", previous_close="39.47"),
                    _bar(index=1, close="39.40", previous_close="39.47"),
                    _bar(
                        event_time=BASE_TIME + timedelta(days=1),
                        close="39.40",
                        previous_close="39.60",
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
                    "limit": 3,
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
    assert payload["performance"]["tradeCount"] == 2
    assert payload["performance"]["fillCount"] == 2
    assert payload["performance"]["endingEquity"] == 99926.3404
    assert len(payload["klineBars"]) == 3
    assert len(payload["equityCurve"]) == 3
    assert "runtimePnlCurve" not in payload
    assert "backtestEquityCurve" not in payload
    assert len(payload["decisions"]) == 3
    assert payload["decisions"][1]["skipReason"] == "sellable_qty_exhausted"


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
    assert payload["decisions"][-1]["reasonSummary"] == "model confirmed the bullish stack"
    assert "OpenAI-compatible" in payload["notes"][0]
