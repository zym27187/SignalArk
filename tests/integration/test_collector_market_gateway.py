from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest
from apps.collector.checkpoints import FileCollectorCheckpointStore
from apps.collector.service import CollectorService
from src.domain.market import NormalizedBar
from src.infra.exchanges import EastmoneyAshareBarGateway, EastmoneyAshareBarNormalizer

SHANGHAI = ZoneInfo("Asia/Shanghai")
BASE_END_LOCAL = datetime(2026, 3, 31, 14, 30, tzinfo=SHANGHAI)
TIMEFRAME = "15m"
STREAM_KEY = "cn_equity:600036.SH:15m"


def _kline_row(
    bar_end_local: datetime,
    *,
    close_price: str,
    open_price: str = "39.47",
    high_price: str = "39.99",
    low_price: str = "39.41",
    volume_lots: str = "26744",
    amount_cny: str = "105520962.00",
    amplitude_pct: str = "1.47",
    pct_change: str = "-0.13",
    change_amount: str = "-0.05",
    turnover_pct: str = "0.31",
) -> str:
    return ",".join(
        [
            bar_end_local.strftime("%Y-%m-%d %H:%M"),
            open_price,
            close_price,
            high_price,
            low_price,
            volume_lots,
            amount_cny,
            amplitude_pct,
            pct_change,
            change_amount,
            turnover_pct,
        ]
    )


def _history_page(rows: list[str]) -> dict[str, object]:
    return {
        "rc": 0,
        "data": {
            "code": "600036",
            "market": 1,
            "name": "招商银行",
            "decimal": 2,
            "klines": rows,
        },
    }


class FakeLiveStreamFactory:
    def __init__(self, attempts: list[list[NormalizedBar | Exception]]) -> None:
        self._attempts = list(attempts)

    def __call__(self, symbols: Sequence[str], timeframe: str) -> AsyncIterator[NormalizedBar]:
        if not self._attempts:
            return self._empty()

        attempt = self._attempts.pop(0)

        async def _iterator() -> AsyncIterator[NormalizedBar]:
            assert list(symbols) == ["600036.SH"]
            assert timeframe == TIMEFRAME
            for item in attempt:
                if isinstance(item, Exception):
                    raise item
                yield item

        return _iterator()

    async def _empty(self) -> AsyncIterator[NormalizedBar]:
        if False:
            yield  # pragma: no cover


def _build_transport(pages: list[list[str]]) -> httpx.MockTransport:
    remaining_pages = list(pages)

    def _handler(request: httpx.Request) -> httpx.Response:
        rows = remaining_pages.pop(0) if remaining_pages else []
        return httpx.Response(200, json=_history_page(rows), request=request)

    return httpx.MockTransport(_handler)


def _build_transport_with_failures(
    attempts: list[list[str] | Exception],
) -> httpx.MockTransport:
    remaining_attempts = list(attempts)

    def _handler(request: httpx.Request) -> httpx.Response:
        attempt = remaining_attempts.pop(0) if remaining_attempts else []
        if isinstance(attempt, Exception):
            raise attempt
        return httpx.Response(200, json=_history_page(attempt), request=request)

    return httpx.MockTransport(_handler)


def _build_jsonp_transport(rows: list[str]) -> httpx.MockTransport:
    def _handler(request: httpx.Request) -> httpx.Response:
        callback = request.url.params.get("cb") or "callback"
        payload = json.dumps(_history_page(rows), ensure_ascii=False)
        return httpx.Response(
            200,
            text=f"{callback}({payload});",
            request=request,
        )

    return httpx.MockTransport(_handler)


async def _collect_events(collector: CollectorService, *, max_events: int) -> list:
    events = []
    async for event in collector.collect_actionable_bars(max_events=max_events):
        events.append(event)
    return events


async def _no_sleep(_: float) -> None:
    return None


def _realtime_bar(
    bar_end_local: datetime,
    *,
    close_price: str,
    closed: bool,
) -> NormalizedBar:
    offset = timedelta(minutes=1) if closed else timedelta(minutes=-5)

    def clock() -> datetime:
        return bar_end_local + offset

    normalizer = EastmoneyAshareBarNormalizer(clock=clock)
    return normalizer.from_kline_row(
        _kline_row(bar_end_local, close_price=close_price),
        symbol="600036.SH",
        timeframe=TIMEFRAME,
        source_kind="realtime",
    )


@pytest.mark.asyncio
async def test_collector_bootstraps_history_and_live_stream_without_duplicate_finals(
    tmp_path,
) -> None:
    bar1_end = BASE_END_LOCAL
    bar2_end = BASE_END_LOCAL + timedelta(minutes=15)

    transport = _build_transport([[_kline_row(bar1_end, close_price="39.42")]])
    client = httpx.AsyncClient(transport=transport, base_url="https://eastmoney.test")
    gateway = EastmoneyAshareBarGateway(
        http_client=client,
        live_stream_factory=FakeLiveStreamFactory(
            [
                [
                    _realtime_bar(bar2_end, close_price="39.55", closed=False),
                    _realtime_bar(bar1_end, close_price="39.42", closed=True),
                    _realtime_bar(bar2_end, close_price="39.55", closed=True),
                ]
            ]
        ),
        clock=lambda: bar2_end + timedelta(hours=1),
    )
    checkpoint_store = FileCollectorCheckpointStore(tmp_path / "collector-checkpoints.json")
    collector = CollectorService(
        gateway,
        exchange="cn_equity",
        symbols=["600036.SH"],
        timeframe=TIMEFRAME,
        checkpoint_store=checkpoint_store,
        reconnect_delay_seconds=0,
        sleep=_no_sleep,
    )

    try:
        events = await _collect_events(collector, max_events=2)
    finally:
        await collector.aclose()
        await client.aclose()

    assert [event.bar_key for event in events] == [
        "cn_equity:600036.SH:15m:2026-03-31T14:15:00+08:00",
        "cn_equity:600036.SH:15m:2026-03-31T14:30:00+08:00",
    ]
    assert [event.source_kind for event in events] == ["historical", "realtime"]
    assert all(event.market_state is not None for event in events)

    checkpoint_state = checkpoint_store.load_state()
    assert checkpoint_state[STREAM_KEY]["last_bar_key"] == events[-1].bar_key


@pytest.mark.asyncio
async def test_collector_retries_bootstrap_backfill_until_history_recovers(
    tmp_path,
) -> None:
    bar1_end = BASE_END_LOCAL
    transport = _build_transport_with_failures(
        [
            httpx.RemoteProtocolError("Server disconnected without sending a response."),
            [_kline_row(bar1_end, close_price="39.42")],
        ]
    )
    client = httpx.AsyncClient(transport=transport, base_url="https://eastmoney.test")
    gateway = EastmoneyAshareBarGateway(
        http_client=client,
        live_stream_factory=FakeLiveStreamFactory([[]]),
        clock=lambda: bar1_end + timedelta(hours=1),
    )
    checkpoint_store = FileCollectorCheckpointStore(tmp_path / "collector-checkpoints.json")
    collector = CollectorService(
        gateway,
        exchange="cn_equity",
        symbols=["600036.SH"],
        timeframe=TIMEFRAME,
        checkpoint_store=checkpoint_store,
        reconnect_delay_seconds=0,
        sleep=_no_sleep,
    )

    try:
        events = await _collect_events(collector, max_events=1)
    finally:
        await collector.aclose()
        await client.aclose()

    assert [event.bar_key for event in events] == [
        "cn_equity:600036.SH:15m:2026-03-31T14:15:00+08:00",
    ]
    assert [event.source_kind for event in events] == ["historical"]

    checkpoint_state = checkpoint_store.load_state()
    assert checkpoint_state[STREAM_KEY]["last_bar_key"] == events[-1].bar_key


@pytest.mark.asyncio
async def test_collector_reconnects_backfills_missing_bars_and_skips_repeated_final_bars(
    tmp_path,
) -> None:
    bar1_end = BASE_END_LOCAL
    bar2_end = BASE_END_LOCAL + timedelta(minutes=15)
    bar3_end = BASE_END_LOCAL + timedelta(minutes=30)
    bar4_end = BASE_END_LOCAL + timedelta(minutes=45)

    transport = _build_transport(
        [
            [_kline_row(bar1_end, close_price="39.42")],
            [
                _kline_row(bar2_end, close_price="39.55"),
                _kline_row(bar3_end, close_price="39.68"),
            ],
        ]
    )
    client = httpx.AsyncClient(transport=transport, base_url="https://eastmoney.test")
    gateway = EastmoneyAshareBarGateway(
        http_client=client,
        live_stream_factory=FakeLiveStreamFactory(
            [
                [
                    _realtime_bar(bar2_end, close_price="39.55", closed=False),
                    RuntimeError("poll disconnected"),
                ],
                [
                    _realtime_bar(bar3_end, close_price="39.68", closed=True),
                    _realtime_bar(bar4_end, close_price="39.80", closed=True),
                ],
            ]
        ),
        clock=lambda: bar4_end + timedelta(hours=1),
    )
    checkpoint_store = FileCollectorCheckpointStore(tmp_path / "collector-checkpoints.json")
    collector = CollectorService(
        gateway,
        exchange="cn_equity",
        symbols=["600036.SH"],
        timeframe=TIMEFRAME,
        checkpoint_store=checkpoint_store,
        reconnect_delay_seconds=0,
        sleep=_no_sleep,
    )

    try:
        events = await _collect_events(collector, max_events=4)
    finally:
        await collector.aclose()
        await client.aclose()

    assert [event.bar_key for event in events] == [
        "cn_equity:600036.SH:15m:2026-03-31T14:15:00+08:00",
        "cn_equity:600036.SH:15m:2026-03-31T14:30:00+08:00",
        "cn_equity:600036.SH:15m:2026-03-31T14:45:00+08:00",
        "cn_equity:600036.SH:15m:2026-03-31T15:00:00+08:00",
    ]
    assert [event.source_kind for event in events] == [
        "historical",
        "historical",
        "historical",
        "realtime",
    ]
    assert all(event.market_state is not None for event in events)

    checkpoint_state = checkpoint_store.load_state()
    assert checkpoint_state[STREAM_KEY]["last_bar_key"] == events[-1].bar_key


@pytest.mark.asyncio
async def test_collector_recovers_when_live_stream_ends_without_exception(
    tmp_path,
) -> None:
    bar1_end = BASE_END_LOCAL

    transport = _build_transport(
        [
            [],
            [_kline_row(bar1_end, close_price="39.42")],
        ]
    )
    client = httpx.AsyncClient(transport=transport, base_url="https://eastmoney.test")
    gateway = EastmoneyAshareBarGateway(
        http_client=client,
        live_stream_factory=FakeLiveStreamFactory([[]]),
        clock=lambda: bar1_end + timedelta(hours=1),
    )
    checkpoint_store = FileCollectorCheckpointStore(tmp_path / "collector-checkpoints.json")
    collector = CollectorService(
        gateway,
        exchange="cn_equity",
        symbols=["600036.SH"],
        timeframe=TIMEFRAME,
        checkpoint_store=checkpoint_store,
        reconnect_delay_seconds=0,
        sleep=_no_sleep,
    )

    try:
        events = await _collect_events(collector, max_events=1)
    finally:
        await collector.aclose()
        await client.aclose()

    assert [event.bar_key for event in events] == [
        "cn_equity:600036.SH:15m:2026-03-31T14:15:00+08:00",
    ]
    assert [event.source_kind for event in events] == ["historical"]

    checkpoint_state = checkpoint_store.load_state()
    assert checkpoint_state[STREAM_KEY]["last_bar_key"] == events[-1].bar_key


@pytest.mark.asyncio
async def test_gateway_decodes_jsonp_history_payloads() -> None:
    client = httpx.AsyncClient(
        transport=_build_jsonp_transport([_kline_row(BASE_END_LOCAL, close_price="39.42")]),
        base_url="https://eastmoney.test",
    )
    gateway = EastmoneyAshareBarGateway(http_client=client)

    try:
        bars = await gateway.fetch_historical_bars("600036.SH", TIMEFRAME, max_bars=1)
    finally:
        await gateway.aclose()
        await client.aclose()

    assert len(bars) == 1
    assert bars[0].symbol == "600036.SH"
    assert bars[0].close == Decimal("39.42")


@pytest.mark.asyncio
async def test_gateway_uses_frontend_style_recent_bar_query_params() -> None:
    seen_params: dict[str, str | None] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        for key in (
            "cb",
            "secid",
            "ut",
            "fields1",
            "fields2",
            "klt",
            "fqt",
            "beg",
            "end",
            "smplmt",
            "lmt",
        ):
            seen_params[key] = request.url.params.get(key)
        payload = json.dumps(
            _history_page([_kline_row(BASE_END_LOCAL, close_price="39.42")]),
            ensure_ascii=False,
        )
        return httpx.Response(
            200,
            text=f"{request.url.params['cb']}({payload});",
            request=request,
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler),
        base_url="https://eastmoney.test",
    )
    gateway = EastmoneyAshareBarGateway(http_client=client)

    try:
        bars = await gateway.fetch_historical_bars("600036.SH", TIMEFRAME, max_bars=8)
    finally:
        await gateway.aclose()
        await client.aclose()

    assert len(bars) == 1
    assert seen_params == {
        "cb": "signalark_jsonp",
        "secid": "1.600036",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "15",
        "fqt": "1",
        "beg": None,
        "end": "20500101",
        "smplmt": None,
        "lmt": "8",
    }


@pytest.mark.asyncio
async def test_gateway_uses_time_bounds_without_recent_bar_limit_for_recovery() -> None:
    seen_params: dict[str, str | None] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        seen_params["cb"] = request.url.params.get("cb")
        seen_params["secid"] = request.url.params.get("secid")
        seen_params["ut"] = request.url.params.get("ut")
        seen_params["klt"] = request.url.params.get("klt")
        seen_params["fqt"] = request.url.params.get("fqt")
        seen_params["beg"] = request.url.params.get("beg")
        seen_params["end"] = request.url.params.get("end")
        seen_params["smplmt"] = request.url.params.get("smplmt")
        seen_params["lmt"] = request.url.params.get("lmt")
        return httpx.Response(
            200,
            json=_history_page([_kline_row(BASE_END_LOCAL, close_price="39.42")]),
            request=request,
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler),
        base_url="https://eastmoney.test",
    )
    gateway = EastmoneyAshareBarGateway(http_client=client)
    start_time = BASE_END_LOCAL - timedelta(days=2)
    end_time = BASE_END_LOCAL

    try:
        bars = await gateway.fetch_historical_bars(
            "600036.SH",
            TIMEFRAME,
            start_time=start_time,
            end_time=end_time,
        )
    finally:
        await gateway.aclose()
        await client.aclose()

    assert len(bars) == 1
    assert seen_params == {
        "cb": "signalark_jsonp",
        "secid": "1.600036",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "klt": "15",
        "fqt": "1",
        "beg": start_time.strftime("%Y%m%d"),
        "end": end_time.strftime("%Y%m%d"),
        "smplmt": "1000000",
        "lmt": "1000000",
    }
