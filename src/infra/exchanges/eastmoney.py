"""Eastmoney A-share market-data adapters for historical and polled realtime bars."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

import httpx

from src.domain.market import NormalizedBar, timeframe_to_timedelta
from src.domain.market.state import (
    SuspensionStatus,
    build_market_state_snapshot,
)
from src.shared.types import shanghai_now

EASTMONEY_REST_BASE_URL = "https://push2his.eastmoney.com"
EASTMONEY_KLINE_ENDPOINT = "/api/qt/stock/kline/get"
EASTMONEY_UT_TOKEN = "fa5fd1943c7b386f172d6893dbfba10b"
EASTMONEY_MAX_KLINES_PER_REQUEST = 1000
EASTMONEY_MAX_SAMPLE_KLINES = 1_000_000
EASTMONEY_JSONP_CALLBACK = "signalark_jsonp"
EASTMONEY_REQUEST_HEADERS = {
    "Accept": "*/*",
    "Referer": "https://quote.eastmoney.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
}
A_SHARE_TIMEZONE = ZoneInfo("Asia/Shanghai")

Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]
LiveStreamFactory = Callable[[Sequence[str], str], AsyncIterator[NormalizedBar]]

TIMEFRAME_TO_KLT = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "60m": "60",
    "1h": "60",
    "1d": "101",
    "1w": "102",
}


def _ensure_shanghai(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must be timezone-aware")
    return value.astimezone(A_SHARE_TIMEZONE)


def _format_history_query_bound(value: datetime | None, *, default: str) -> str:
    """Format optional Eastmoney beg/end query bounds using Shanghai-local dates."""
    if value is None:
        return default
    return _ensure_shanghai(value).strftime("%Y%m%d")


def _normalize_symbol_to_secid(symbol: str) -> tuple[str, str]:
    normalized = symbol.strip().upper()
    if "." not in normalized:
        raise ValueError("A-share symbols must include venue suffix like .SH or .SZ")

    code, venue = normalized.split(".", maxsplit=1)
    market_prefix = {"SH": "1", "SZ": "0"}.get(venue)
    if market_prefix is None:
        raise ValueError(f"Unsupported A-share venue suffix: {venue}")

    if not code.isdigit():
        raise ValueError(f"A-share symbol code must be numeric: {symbol}")

    return normalized, f"{market_prefix}.{code}"


def _normalize_timeframe_to_klt(timeframe: str) -> str:
    normalized = timeframe.strip().lower()
    klt = TIMEFRAME_TO_KLT.get(normalized)
    if klt is None:
        raise ValueError(f"Unsupported Eastmoney timeframe: {timeframe}")
    return klt


def _parse_local_bar_end_time(value: str) -> datetime:
    normalized = value.strip()
    formats = ("%Y-%m-%d %H:%M", "%Y-%m-%d")
    for candidate in formats:
        try:
            parsed = datetime.strptime(normalized, candidate)
            if candidate == "%Y-%m-%d":
                parsed = parsed.replace(hour=15, minute=0)
            return parsed.replace(tzinfo=A_SHARE_TIMEZONE)
        except ValueError:
            continue

    raise ValueError(f"Unsupported Eastmoney kline timestamp: {value}")


def _rule_decimal(rule: object, field_name: str) -> Decimal | None:
    if isinstance(rule, Mapping):
        raw_value = rule.get(field_name)
    else:
        raw_value = getattr(rule, field_name, None)

    if raw_value is None:
        return None
    return Decimal(str(raw_value))


def _decode_eastmoney_payload(raw: str) -> dict[str, object]:
    """Accept both bare JSON and JSONP payloads used by Eastmoney quote pages."""
    text = raw.strip()
    if not text:
        return {}

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.fullmatch(r"[\w$.]+\((.*)\)\s*;?", text, flags=re.DOTALL)
        if match is None:
            raise ValueError("Eastmoney response is neither JSON nor JSONP.") from None
        payload = json.loads(match.group(1))

    if not isinstance(payload, dict):
        raise ValueError("Eastmoney response payload must be a JSON object.")

    return payload


class EastmoneyAshareBarNormalizer:
    """Normalize Eastmoney K-line payloads into exchange-agnostic bar models."""

    def __init__(
        self,
        *,
        clock: Clock = shanghai_now,
        symbol_rules: Mapping[str, object] | None = None,
        default_price_limit_pct: Decimal = Decimal("0.10"),
        default_price_tick: Decimal = Decimal("0.01"),
    ) -> None:
        self._clock = clock
        self._symbol_rules = {
            str(symbol).strip().upper(): rule for symbol, rule in (symbol_rules or {}).items()
        }
        self._default_price_limit_pct = default_price_limit_pct
        self._default_price_tick = default_price_tick

    def _resolve_price_limit_pct(self, symbol: str, explicit_value: Decimal | None) -> Decimal:
        if explicit_value is not None:
            return explicit_value
        rule = self._symbol_rules.get(symbol.strip().upper())
        return _rule_decimal(rule, "price_limit_pct") or self._default_price_limit_pct

    def _resolve_price_tick(self, symbol: str, explicit_value: Decimal | None) -> Decimal:
        if explicit_value is not None:
            return explicit_value
        rule = self._symbol_rules.get(symbol.strip().upper())
        return _rule_decimal(rule, "price_tick") or self._default_price_tick

    def from_kline_row(
        self,
        row: str,
        *,
        symbol: str,
        timeframe: str,
        secid: str | None = None,
        source_kind: Literal["historical", "realtime"],
        previous_close: Decimal | None = None,
        price_limit_pct: Decimal | None = None,
        price_tick: Decimal | None = None,
    ) -> NormalizedBar:
        """Convert one Eastmoney kline row into the project's normalized bar contract."""
        parts = [item.strip() for item in row.split(",")]
        if len(parts) < 7:
            raise ValueError("Eastmoney kline rows must contain at least 7 comma-separated fields")

        normalized_symbol, resolved_secid = _normalize_symbol_to_secid(symbol)
        ingest_time = _ensure_shanghai(self._clock())
        bar_end_time = _parse_local_bar_end_time(parts[0])
        bar_start_time = bar_end_time - timeframe_to_timedelta(timeframe)
        close_price = Decimal(parts[2])
        volume_shares = Decimal(parts[5]) * Decimal("100")
        amount_cny = Decimal(parts[6])
        closed = ingest_time >= bar_end_time
        change_amount = Decimal(parts[9]) if len(parts) >= 10 and parts[9] else None
        resolved_previous_close = previous_close
        if resolved_previous_close is None and change_amount is not None:
            resolved_previous_close = close_price - change_amount

        resolved_price_limit_pct = self._resolve_price_limit_pct(
            normalized_symbol,
            price_limit_pct,
        )
        resolved_price_tick = self._resolve_price_tick(normalized_symbol, price_tick)
        market_state = None
        if resolved_previous_close is not None and resolved_previous_close > 0:
            suspension_status = (
                SuspensionStatus.UNKNOWN
                if volume_shares == 0 and amount_cny == 0
                else SuspensionStatus.ACTIVE
            )
            market_state = build_market_state_snapshot(
                event_time=bar_end_time,
                previous_close=resolved_previous_close,
                price_limit_pct=resolved_price_limit_pct,
                price_tick=resolved_price_tick,
                suspension_status=suspension_status,
            )

        source_payload = {
            "source": "eastmoney_kline",
            "secid": secid or resolved_secid,
            "symbol": normalized_symbol,
            "interval": timeframe,
            "bar_end_time_local": parts[0],
            "open": parts[1],
            "close": parts[2],
            "high": parts[3],
            "low": parts[4],
            "volume_lots": parts[5],
            "volume_shares": str(volume_shares),
            "amount_cny": parts[6],
            "raw_kline": row,
        }
        optional_payload_fields = {
            "amplitude_pct": parts[7] if len(parts) >= 8 else None,
            "pct_change": parts[8] if len(parts) >= 9 else None,
            "change_amount": parts[9] if len(parts) >= 10 else None,
            "turnover_pct": parts[10] if len(parts) >= 11 else None,
            "previous_close": (
                str(resolved_previous_close) if resolved_previous_close is not None else None
            ),
            "market_state": (
                market_state.model_dump(mode="json") if market_state is not None else None
            ),
        }
        source_payload.update(
            {key: value for key, value in optional_payload_fields.items() if value is not None}
        )

        return NormalizedBar(
            exchange="cn_equity",
            symbol=normalized_symbol,
            timeframe=timeframe,
            bar_start_time=bar_start_time,
            bar_end_time=bar_end_time,
            ingest_time=ingest_time,
            open=parts[1],
            close=parts[2],
            high=parts[3],
            low=parts[4],
            volume=volume_shares,
            quote_volume=amount_cny,
            trade_count=None,
            closed=closed,
            final=closed,
            source_kind=source_kind,
            market_state=market_state,
            source_payload=source_payload,
        )


class EastmoneyAshareBarGateway:
    """Fetch Eastmoney A-share K-lines and expose them as normalized bars."""

    def __init__(
        self,
        *,
        rest_base_url: str = EASTMONEY_REST_BASE_URL,
        http_client: httpx.AsyncClient | None = None,
        live_stream_factory: LiveStreamFactory | None = None,
        live_poll_bars: int = 8,
        poll_interval_seconds: float = 5.0,
        clock: Clock = shanghai_now,
        sleep: Sleep = asyncio.sleep,
        symbol_rules: Mapping[str, object] | None = None,
        default_price_limit_pct: Decimal = Decimal("0.10"),
        default_price_tick: Decimal = Decimal("0.01"),
    ) -> None:
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            base_url=rest_base_url,
            timeout=10.0,
            headers=EASTMONEY_REQUEST_HEADERS,
        )
        self._live_stream_factory = live_stream_factory
        self._live_poll_bars = live_poll_bars
        self._poll_interval_seconds = poll_interval_seconds
        self._sleep = sleep
        self._symbol_rules = {
            str(symbol).strip().upper(): rule for symbol, rule in (symbol_rules or {}).items()
        }
        self._normalizer = EastmoneyAshareBarNormalizer(
            clock=clock,
            symbol_rules=self._symbol_rules,
            default_price_limit_pct=default_price_limit_pct,
            default_price_tick=default_price_tick,
        )

    async def aclose(self) -> None:
        """Close owned transport resources."""
        if self._owns_http_client:
            await self._http_client.aclose()

    async def fetch_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_bars: int | None = None,
    ) -> list[NormalizedBar]:
        """Fetch recent Eastmoney K-lines and filter them into the requested window."""
        return await self._fetch_bars(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            max_bars=max_bars,
            source_kind="historical",
        )

    async def stream_live_bars(
        self,
        symbols: Sequence[str],
        timeframe: str,
    ) -> AsyncIterator[NormalizedBar]:
        """Poll the latest Eastmoney bars and stream them as realtime updates."""
        if self._live_stream_factory is not None:
            async for bar in self._live_stream_factory(symbols, timeframe):
                yield bar
            return

        while True:
            for symbol in symbols:
                bars = await self._fetch_bars(
                    symbol=symbol,
                    timeframe=timeframe,
                    max_bars=self._live_poll_bars,
                    source_kind="realtime",
                )
                for bar in bars:
                    yield bar

            await self._sleep(self._poll_interval_seconds)

    async def _fetch_bars(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_bars: int | None = None,
        source_kind: Literal["historical", "realtime"],
    ) -> list[NormalizedBar]:
        normalized_symbol, secid = _normalize_symbol_to_secid(symbol)
        has_time_bounds = start_time is not None or end_time is not None
        params = {
            "cb": EASTMONEY_JSONP_CALLBACK,
            "secid": secid,
            "ut": EASTMONEY_UT_TOKEN,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": _normalize_timeframe_to_klt(timeframe),
            "fqt": "1",
            "beg": _format_history_query_bound(start_time, default="0"),
            "end": _format_history_query_bound(end_time, default="20500101"),
            "smplmt": str(EASTMONEY_MAX_SAMPLE_KLINES),
            "lmt": str(EASTMONEY_MAX_SAMPLE_KLINES),
        }
        if max_bars is not None:
            params["lmt"] = str(max_bars)
            if not has_time_bounds:
                # Mirror the quote page's "lastcount" shortcut for recent-bar queries.
                params.pop("beg", None)
                params.pop("smplmt", None)

        response = await self._http_client.get(EASTMONEY_KLINE_ENDPOINT, params=params)
        response.raise_for_status()

        payload = _decode_eastmoney_payload(response.text)
        data = payload.get("data") if isinstance(payload, dict) else None
        klines = data.get("klines") if isinstance(data, dict) else None
        if klines is None:
            return []
        if not isinstance(klines, list):
            raise ValueError("Eastmoney kline response data.klines must be a list")

        bars: list[NormalizedBar] = []
        prior_close: Decimal | None = None
        for row in klines:
            bar = self._normalizer.from_kline_row(
                row,
                symbol=normalized_symbol,
                timeframe=timeframe,
                secid=secid,
                source_kind=source_kind,
                previous_close=prior_close,
            )
            bars.append(bar)
            prior_close = bar.close

        bars.sort(key=lambda bar: bar.bar_start_time)

        if start_time is not None:
            start_time = _ensure_shanghai(start_time)
            bars = [bar for bar in bars if bar.bar_start_time >= start_time]
        if end_time is not None:
            end_time = _ensure_shanghai(end_time)
            bars = [bar for bar in bars if bar.bar_end_time <= end_time]
        if max_bars is not None:
            bars = bars[-max_bars:]

        return bars
