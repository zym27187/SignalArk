"""Minimal control-plane service used by the Phase 6B API."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import sessionmaker
from src.config import Settings
from src.domain.events import BarEvent
from src.domain.execution import OrderSide, OrderStatus
from src.domain.market import NormalizedBar
from src.domain.reconciliation import ReplayEventFilters
from src.infra.db import SqlAlchemyRepositories, session_scope
from src.infra.db.models import (
    BalanceSnapshotRecord,
    FillRecord,
    OrderIntentRecord,
    OrderRecord,
)
from src.infra.exchanges import EastmoneyAshareBarGateway
from src.infra.observability import SignalArkObservability, build_observability
from src.shared.types import SHANGHAI_TIMEZONE, shanghai_now

from apps.research import build_default_backtest_runner
from apps.research.snapshot import build_web_snapshot_payload
from apps.trader.control_plane import TraderControlPlaneStore
from apps.trader.oms import build_default_trader_oms_service
from apps.trader.reconciliation import SessionFactoryBackedReconciliationStore

READ_ONLY_MARKET_TIMEFRAMES = frozenset({"15m", "1h"})
DEFAULT_RESEARCH_INITIAL_CASH = Decimal("100000")
DEFAULT_RESEARCH_SLIPPAGE_BPS = Decimal("5")


def _is_missing_persistence_table_error(exc: Exception) -> bool:
    """Treat uninitialized persistence tables as an empty-state API response."""
    if not isinstance(exc, (OperationalError, ProgrammingError)):
        return False

    original_error = getattr(exc, "orig", None)
    message = " ".join(
        part
        for part in (
            str(exc),
            str(original_error) if original_error is not None else "",
            type(original_error).__name__ if original_error is not None else "",
        )
        if part
    ).lower()
    return any(
        marker in message
        for marker in (
            "no such table",
            "does not exist",
            "undefinedtable",
            "undefined table",
        )
    )


class ApiControlPlaneService:
    """Coordinate DB-backed status queries and operator actions."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker,
        control_store: TraderControlPlaneStore,
        observability: SignalArkObservability | None = None,
        market_gateway_factory: Callable[[], HistoricalBarGateway] | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._control_store = control_store
        self._observability = observability or build_observability(
            settings=settings,
            service="api",
            logger_name="signalark.api.control_plane",
        )
        self._reconciliation_store = SessionFactoryBackedReconciliationStore(session_factory)
        self._market_gateway_factory = market_gateway_factory or (
            lambda: EastmoneyAshareBarGateway(symbol_rules=settings.symbol_rules)
        )

    def live_payload(self) -> dict[str, object]:
        database_connected = False
        try:
            database_connected = self._control_store.ping()
        except Exception:
            database_connected = False
        return {
            "status": "alive",
            "service": self._settings.app_name,
            "database_connected": database_connected,
        }

    def ready_payload(self) -> dict[str, object]:
        try:
            return self._control_store.build_status_view(
                account_id=self._settings.account_id,
                timeframe=self._settings.primary_timeframe,
                market_stale_threshold_seconds=self._settings.market_stale_threshold_seconds,
            )
        except Exception as exc:
            return {
                "status": "not_ready",
                "ready": False,
                "account_id": self._settings.account_id,
                "message": str(exc),
            }

    def status_payload(self) -> dict[str, object]:
        payload = self.ready_payload()
        payload.update(
            {
                "service": self._settings.app_name,
                "env": self._settings.env,
                "execution_mode": self._settings.execution_mode,
                "exchange": self._settings.exchange,
                "symbols": self._settings.symbols,
            }
        )
        return payload

    def positions_payload(self) -> dict[str, object]:
        try:
            with session_scope(self._session_factory) as session:
                repositories = SqlAlchemyRepositories.from_session(session)
                positions = repositories.recovery.load_runtime_state(
                    account_id=self._settings.account_id,
                    event_limit=0,
                ).open_positions
        except Exception as exc:
            if _is_missing_persistence_table_error(exc):
                positions = ()
            else:
                raise
        return {
            "account_id": self._settings.account_id,
            "positions": [position.model_dump(mode="json") for position in positions],
        }

    def active_orders_payload(self) -> dict[str, object]:
        try:
            with session_scope(self._session_factory) as session:
                query = (
                    select(OrderRecord, OrderIntentRecord.reduce_only)
                    .join(OrderIntentRecord, OrderIntentRecord.id == OrderRecord.order_intent_id)
                    .where(OrderRecord.account_id == self._settings.account_id)
                    .where(
                        OrderRecord.status.in_(
                            (
                                OrderStatus.NEW.value,
                                OrderStatus.ACK.value,
                                OrderStatus.PARTIALLY_FILLED.value,
                            )
                        )
                    )
                    .order_by(OrderRecord.updated_at.asc(), OrderRecord.id.asc())
                )
                rows = session.execute(query).all()
        except Exception as exc:
            if _is_missing_persistence_table_error(exc):
                rows = ()
            else:
                raise
        return {
            "account_id": self._settings.account_id,
            "orders": [
                {
                    "order_id": order_record.id,
                    "order_intent_id": order_record.order_intent_id,
                    "symbol": order_record.symbol,
                    "side": order_record.side,
                    "order_type": order_record.order_type,
                    "qty": order_record.qty,
                    "filled_qty": order_record.filled_qty,
                    "status": order_record.status,
                    "reduce_only": reduce_only,
                    "submitted_at": order_record.submitted_at.isoformat(),
                    "updated_at": order_record.updated_at.isoformat(),
                }
                for order_record, reduce_only in rows
            ],
        }

    async def market_bars_payload(
        self,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: int = 96,
    ) -> dict[str, object]:
        resolved_symbol = self._resolve_symbol(symbol)
        resolved_timeframe = self._resolve_timeframe(timeframe)
        bars = await self._fetch_historical_bars(
            symbol=resolved_symbol,
            timeframe=resolved_timeframe,
            limit=limit,
        )
        return {
            "symbol": resolved_symbol,
            "timeframe": resolved_timeframe,
            "count": len(bars),
            "source": "eastmoney_historical",
            "bars": [
                {
                    "time": bar.bar_end_time.isoformat(),
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": float(bar.volume),
                }
                for bar in bars
            ],
        }

    async def equity_curve_payload(
        self,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: int = 96,
    ) -> dict[str, object]:
        resolved_symbol = self._resolve_symbol(symbol)
        resolved_timeframe = self._resolve_timeframe(timeframe)

        try:
            with session_scope(self._session_factory) as session:
                balance_rows = tuple(
                    session.scalars(
                        select(BalanceSnapshotRecord)
                        .where(BalanceSnapshotRecord.account_id == self._settings.account_id)
                        .where(BalanceSnapshotRecord.asset == "CNY")
                        .order_by(
                            BalanceSnapshotRecord.snapshot_time.asc(),
                            BalanceSnapshotRecord.id.asc(),
                        )
                    )
                )
                fill_rows = tuple(
                    session.scalars(
                        select(FillRecord)
                        .where(FillRecord.account_id == self._settings.account_id)
                        .order_by(FillRecord.fill_time.asc(), FillRecord.id.asc())
                    )
                )
        except Exception as exc:
            if _is_missing_persistence_table_error(exc):
                balance_rows = ()
                fill_rows = ()
            else:
                raise

        valuation_symbols = _resolve_portfolio_valuation_symbols(
            anchor_symbol=resolved_symbol,
            configured_symbols=self._settings.symbols,
            fill_rows=fill_rows,
        )
        bars_by_symbol = await self._fetch_historical_bars_by_symbol(
            symbols=valuation_symbols,
            timeframe=resolved_timeframe,
            limit=limit,
        )
        points = _build_portfolio_equity_curve_points(
            bars_by_symbol=bars_by_symbol,
            balance_rows=balance_rows,
            fill_rows=fill_rows,
        )
        return {
            "account_id": self._settings.account_id,
            "symbol": resolved_symbol,
            "timeframe": resolved_timeframe,
            "count": len(points),
            "source": "balance_snapshots_plus_portfolio_market_bars",
            "scope": "account_portfolio",
            "anchor_symbol": resolved_symbol,
            "valuation_symbols": list(valuation_symbols),
            "points": points,
        }

    async def research_snapshot_payload(
        self,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: int = 96,
    ) -> dict[str, object]:
        resolved_symbol = self._resolve_symbol(symbol)
        resolved_timeframe = self._resolve_timeframe(timeframe)
        bars = await self._fetch_historical_bars(
            symbol=resolved_symbol,
            timeframe=resolved_timeframe,
            limit=limit,
        )
        backtest_bars = _build_research_backtest_bars(bars)
        if not backtest_bars:
            raise LookupError("No finalized bars are available to build a research snapshot yet.")

        runner = build_default_backtest_runner(
            self._settings,
            initial_cash=DEFAULT_RESEARCH_INITIAL_CASH,
            slippage_bps=DEFAULT_RESEARCH_SLIPPAGE_BPS,
        )
        result = await runner.run(backtest_bars)
        return build_web_snapshot_payload(
            result=result,
            bars=backtest_bars,
            source_label="由 research API 生成的真实回测结果",
            source_mode="live",
            notes=(
                "该快照由 `/v1/research/snapshot` 基于真实历史 K 线即时生成。",
                "当前 research 页已直接消费后端回测结果，不再固定停留在本地 fixture 页面。",
                "当前 runtimePnlCurve 仍与 backtestEquityCurve 共用同一条回测权益曲线。",
            ),
        )

    async def pause_strategy(self) -> dict[str, object]:
        snapshot = self._control_store.set_strategy_enabled(
            account_id=self._settings.account_id,
            enabled=False,
        )
        return self._control_action_response(
            accepted=True,
            message="Strategy paused.",
            control_state=snapshot.control_state.value,
            event_name="control.strategy_paused",
            reason_code="OPERATOR_REQUEST",
        )

    async def resume_strategy(self) -> dict[str, object]:
        snapshot = self._control_store.set_strategy_enabled(
            account_id=self._settings.account_id,
            enabled=True,
        )
        return self._control_action_response(
            accepted=True,
            message="Strategy resumed.",
            control_state=snapshot.control_state.value,
            event_name="control.strategy_resumed",
            reason_code="OPERATOR_REQUEST",
        )

    async def enable_kill_switch(self) -> dict[str, object]:
        snapshot = self._control_store.set_kill_switch(
            account_id=self._settings.account_id,
            active=True,
        )
        return self._control_action_response(
            accepted=True,
            message="Kill switch enabled; only reducing or flattening actions remain allowed.",
            control_state=snapshot.control_state.value,
            event_name="control.kill_switch_enabled",
            severity="warning",
            notify=True,
            reason_code="OPERATOR_REQUEST",
        )

    async def disable_kill_switch(self) -> dict[str, object]:
        snapshot = self._control_store.set_kill_switch(
            account_id=self._settings.account_id,
            active=False,
        )
        return self._control_action_response(
            accepted=True,
            message="Kill switch disabled; protection mode, if active, is unchanged.",
            control_state=snapshot.control_state.value,
            event_name="control.kill_switch_disabled",
            notify=True,
            reason_code="OPERATOR_REQUEST",
        )

    async def cancel_all(self) -> dict[str, object]:
        snapshot = self._control_store.mark_cancel_all_requested(
            account_id=self._settings.account_id,
        )
        oms_service = build_default_trader_oms_service(
            settings=self._settings,
            session_factory=self._session_factory,
            control_store=self._control_store,
            observability=self._observability,
        )
        try:
            result = await oms_service.cancel_all_orders(
                account_id=self._settings.account_id,
                control_state=snapshot.control_state,
            )
        except Exception as exc:
            self._observability.emit(
                event_name="control.cancel_all_failed",
                severity="critical",
                message="Cancel-all failed before all eligible orders could be cancelled.",
                notify=True,
                bypass_cooldown=True,
                account_id=self._settings.account_id,
                control_state=snapshot.control_state.value,
                reason_code="CANCEL_ALL_FAILED",
                details={"error": str(exc)},
            )
            raise
        response = self._control_action_response(
            accepted=True,
            message="Cancel-all request applied to active orders.",
            control_state=snapshot.control_state.value,
            event_name="control.cancel_all_requested",
            severity="warning",
            notify=True,
            reason_code="OPERATOR_REQUEST",
            details={
                "requested_order_count": result.requested_order_count,
                "cancelled_order_count": result.cancelled_order_count,
                "skipped_order_count": result.skipped_order_count,
            },
        )
        response.update(
            {
                "requested_order_count": result.requested_order_count,
                "cancelled_order_count": result.cancelled_order_count,
                "skipped_order_count": result.skipped_order_count,
            }
        )
        return response

    def replay_events_payload(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        trader_run_id: UUID | None = None,
        account_id: str | None = None,
        symbol: str | None = None,
        limit: int = 200,
    ) -> dict[str, object]:
        filters = ReplayEventFilters(
            start_time=start_time,
            end_time=end_time,
            trader_run_id=trader_run_id,
            account_id=account_id or self._settings.account_id,
            symbol=symbol,
            limit=limit,
        )
        try:
            events = self._reconciliation_store.replay_events(filters)
        except Exception as exc:
            if _is_missing_persistence_table_error(exc):
                events = ()
            else:
                raise
        return {
            "filters": filters.model_dump(mode="json"),
            "count": len(events),
            "events": [event.model_dump(mode="json") for event in events],
        }

    def _resolve_symbol(self, symbol: str | None) -> str:
        resolved = (symbol or self._settings.symbols[0]).strip().upper()
        if resolved not in self._settings.supported_symbols:
            raise ValueError(f"Unsupported symbol: {resolved}")
        return resolved

    def _resolve_timeframe(self, timeframe: str | None) -> str:
        resolved = (timeframe or self._settings.primary_timeframe).strip().lower()
        if resolved not in READ_ONLY_MARKET_TIMEFRAMES:
            raise ValueError(
                f"Unsupported timeframe: {resolved}; "
                f"supported values are {', '.join(sorted(READ_ONLY_MARKET_TIMEFRAMES))}."
            )
        return resolved

    async def _fetch_historical_bars(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> list[NormalizedBar]:
        gateway = self._market_gateway_factory()
        try:
            return await gateway.fetch_historical_bars(
                symbol=symbol,
                timeframe=timeframe,
                max_bars=limit,
            )
        finally:
            await gateway.aclose()

    async def _fetch_historical_bars_by_symbol(
        self,
        *,
        symbols: tuple[str, ...],
        timeframe: str,
        limit: int,
    ) -> dict[str, tuple[NormalizedBar, ...]]:
        gateway = self._market_gateway_factory()
        try:
            bars_by_symbol: dict[str, tuple[NormalizedBar, ...]] = {}
            for symbol in symbols:
                bars_by_symbol[symbol] = tuple(
                    await gateway.fetch_historical_bars(
                        symbol=symbol,
                        timeframe=timeframe,
                        max_bars=limit,
                    )
                )
            return bars_by_symbol
        finally:
            await gateway.aclose()

    def _control_action_response(
        self,
        *,
        accepted: bool,
        message: str,
        control_state: str,
        event_name: str | None = None,
        severity: str = "info",
        notify: bool = False,
        reason_code: str | None = None,
        details: dict[str, object] | None = None,
    ) -> dict[str, object]:
        status_payload = self._control_store.build_status_view(
            account_id=self._settings.account_id,
            timeframe=self._settings.primary_timeframe,
            market_stale_threshold_seconds=self._settings.market_stale_threshold_seconds,
        )
        response = {
            "accepted": accepted,
            "control_state": control_state,
            "trader_run_id": status_payload.get("trader_run_id"),
            "instance_id": status_payload.get("instance_id"),
            "effective_at": shanghai_now().isoformat(),
            "message": message,
        }
        if event_name is not None:
            self._observability.emit(
                event_name=event_name,
                severity=severity,
                message=message,
                notify=notify,
                trader_run_id=status_payload.get("trader_run_id"),
                instance_id=status_payload.get("instance_id"),
                account_id=self._settings.account_id,
                exchange=self._settings.exchange,
                control_state=control_state,
                reason_code=reason_code,
                details=details,
            )
        return response


class HistoricalBarGateway(Protocol):
    """Async market-data contract used by the API read endpoints."""

    async def fetch_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        max_bars: int | None = None,
    ) -> list[NormalizedBar]: ...

    async def aclose(self) -> None: ...


def _as_shanghai_datetime(value: datetime) -> datetime:
    """Normalize ORM-loaded timestamps back to timezone-aware Shanghai datetimes."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=SHANGHAI_TIMEZONE)
    return value.astimezone(SHANGHAI_TIMEZONE)


def _build_portfolio_equity_curve_points(
    *,
    bars_by_symbol: dict[str, tuple[NormalizedBar, ...]] | dict[str, list[NormalizedBar]],
    balance_rows: tuple[BalanceSnapshotRecord, ...],
    fill_rows: tuple[FillRecord, ...],
) -> list[dict[str, float | str]]:
    if not balance_rows:
        return []

    snapshots = [(_as_shanghai_datetime(row.snapshot_time), row.total) for row in balance_rows]
    baseline = float(snapshots[0][1])

    timeline = sorted(
        {
            _as_shanghai_datetime(bar.bar_end_time)
            for symbol_bars in bars_by_symbol.values()
            for bar in symbol_bars
        }
    )
    if not timeline:
        return [
            {
                "time": snapshot_time.isoformat(),
                "value": float(total),
                "baseline": baseline,
            }
            for snapshot_time, total in snapshots
        ]

    points: list[dict[str, float | str]] = []
    snapshot_index = 0
    fill_index = 0
    position_qty_by_symbol: dict[str, Decimal] = {}
    last_fill_price_by_symbol: dict[str, Decimal] = {}
    latest_mark_price_by_symbol: dict[str, Decimal] = {}
    snapshot_count = len(snapshots)
    bar_indices = {symbol: 0 for symbol in bars_by_symbol}
    normalized_fills = [
        (
            _as_shanghai_datetime(row.fill_time),
            OrderSide(row.side),
            row.symbol,
            row.qty,
            row.price,
        )
        for row in fill_rows
    ]

    for bar_time in timeline:
        while snapshot_index + 1 < snapshot_count and snapshots[snapshot_index + 1][0] <= bar_time:
            snapshot_index += 1
        if snapshots[snapshot_index][0] > bar_time:
            continue

        while fill_index < len(normalized_fills) and normalized_fills[fill_index][0] <= bar_time:
            _, side, symbol, qty, price = normalized_fills[fill_index]
            current_qty = position_qty_by_symbol.get(symbol, Decimal("0"))
            if side is OrderSide.BUY:
                position_qty_by_symbol[symbol] = current_qty + qty
            else:
                position_qty_by_symbol[symbol] = current_qty - qty
            if position_qty_by_symbol[symbol] <= 0:
                position_qty_by_symbol.pop(symbol, None)
            last_fill_price_by_symbol[symbol] = price
            fill_index += 1

        for symbol, symbol_bars in bars_by_symbol.items():
            bar_index = bar_indices[symbol]
            while (
                bar_index < len(symbol_bars)
                and _as_shanghai_datetime(symbol_bars[bar_index].bar_end_time) <= bar_time
            ):
                latest_mark_price_by_symbol[symbol] = symbol_bars[bar_index].close
                bar_index += 1
            bar_indices[symbol] = bar_index

        cash = snapshots[snapshot_index][1]
        market_value = Decimal("0")
        for symbol, qty in position_qty_by_symbol.items():
            mark_price = latest_mark_price_by_symbol.get(symbol)
            if mark_price is None:
                mark_price = last_fill_price_by_symbol.get(symbol)
            if mark_price is None:
                continue
            market_value += qty * mark_price
        equity = cash + market_value
        points.append(
            {
                "time": bar_time.isoformat(),
                "value": float(equity),
                "baseline": baseline,
            }
        )

    if points:
        first_value = points[0]["value"]
        for point in points:
            point["baseline"] = first_value

    return points


def _resolve_portfolio_valuation_symbols(
    *,
    anchor_symbol: str,
    configured_symbols: list[str] | tuple[str, ...],
    fill_rows: tuple[FillRecord, ...],
) -> tuple[str, ...]:
    ordered_symbols: list[str] = []

    def remember(symbol: str) -> None:
        normalized = symbol.strip().upper()
        if normalized and normalized not in ordered_symbols:
            ordered_symbols.append(normalized)

    remember(anchor_symbol)
    for symbol in configured_symbols:
        remember(symbol)
    for row in fill_rows:
        remember(row.symbol)
    return tuple(ordered_symbols)


def _build_research_backtest_bars(
    bars: tuple[NormalizedBar, ...] | list[NormalizedBar],
) -> tuple[BarEvent, ...]:
    ordered_bars = sorted(
        bars,
        key=lambda item: (
            item.bar_end_time,
            item.bar_start_time,
            item.ingest_time,
            item.bar_key,
        ),
    )
    seen_bar_keys: set[str] = set()
    events: list[BarEvent] = []
    for bar in ordered_bars:
        if not bar.actionable or bar.bar_key in seen_bar_keys:
            continue
        seen_bar_keys.add(bar.bar_key)
        events.append(bar.to_bar_event())
    return tuple(events)
