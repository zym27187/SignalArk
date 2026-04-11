"""Minimal control-plane service used by the Phase 6B API."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import sessionmaker
from src.config import Settings
from src.config.shared_contracts import build_shared_contracts_payload
from src.domain.events import BarEvent
from src.domain.execution import OrderSide, OrderStatus
from src.domain.market import NormalizedBar
from src.domain.portfolio import BalanceSnapshot, Position
from src.domain.reconciliation import ReplayEventFilters
from src.domain.strategy import AI_BAR_JUDGE_V1, load_ai_bar_judge_config
from src.domain.strategy.ai import (
    HEURISTIC_STUB,
    OPENAI_CHAT_COMPLETIONS,
    AiBarJudgeStrategy,
    OpenAiCompatibleDecisionProvider,
)
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
from apps.research.analysis import (
    ResearchSamplePurpose,
    build_sample_metadata,
    build_segment_analyses,
    resolve_sample_bar_limit,
)
from apps.research.snapshot import build_web_snapshot_payload
from apps.trader.control_plane import (
    MissingControlPlaneSchemaError,
    ResearchAiSettingsSnapshot,
    RuntimeSymbolRequestSnapshot,
    TraderControlPlaneStore,
)
from apps.trader.oms import build_default_trader_oms_service
from apps.trader.reconciliation import SessionFactoryBackedReconciliationStore

READ_ONLY_MARKET_TIMEFRAMES = frozenset({"15m", "1h"})
DEFAULT_RESEARCH_INITIAL_CASH = Decimal("100000")
DEFAULT_RESEARCH_SLIPPAGE_BPS = Decimal("5")
DEFAULT_AI_RESEARCH_PROVIDER_TIMEOUT_SECONDS = 30.0
ASHARE_SYMBOL_PATTERN = re.compile(r"^\d{6}\.(SH|SZ)$")


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

    def _default_status_payload(self, *, message: str | None = None) -> dict[str, object]:
        """Keep `/health/ready` and `/v1/status` shape stable during empty-state startup."""
        payload = {
            "trader_run_id": None,
            "instance_id": None,
            "account_id": self._settings.account_id,
            "control_state": "normal",
            "strategy_enabled": True,
            "kill_switch_active": False,
            "protection_mode_active": False,
            "ready": False,
            "status": "not_ready",
            "health_status": "unknown",
            "lifecycle_status": "stopped",
            "market_data_fresh": False,
            "market_state_available": False,
            "latest_final_bar_time": None,
            "current_trading_phase": None,
            "lease_owner_instance_id": None,
            "lease_expires_at": None,
            "last_heartbeat_at": None,
            "fencing_token": None,
            "last_cancel_all_at": None,
            "cancel_all_token": 0,
            "message": message,
        }
        payload["degraded_mode"] = _build_fallback_degraded_mode_payload(
            settings=self._settings,
            effective_at=shanghai_now().isoformat(),
            message=message,
        )
        return payload

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
            return self._status_view_with_diagnostics()
        except Exception as exc:
            return self._default_status_payload(message=str(exc))

    def degraded_mode_payload(self) -> dict[str, object]:
        try:
            status_payload = self._control_store.build_status_view(
                account_id=self._settings.account_id,
                timeframe=self._settings.primary_timeframe,
                market_stale_threshold_seconds=self._settings.market_stale_threshold_seconds,
            )
            return _build_degraded_mode_payload(
                settings=self._settings,
                status_payload=status_payload,
            )
        except Exception as exc:
            return _build_fallback_degraded_mode_payload(
                settings=self._settings,
                effective_at=shanghai_now().isoformat(),
                message=str(exc),
            )

    def status_payload(self) -> dict[str, object]:
        payload = self.ready_payload()
        payload.update(
            {
                "service": self._settings.app_name,
                "env": self._settings.env,
                "execution_mode": self._settings.execution_mode,
                "exchange": self._settings.exchange,
                "symbols": self._settings.symbols,
                "symbol_names": self._settings.symbol_names,
            }
        )
        return payload

    def _status_view_with_diagnostics(self) -> dict[str, object]:
        payload = self._control_store.build_status_view(
            account_id=self._settings.account_id,
            timeframe=self._settings.primary_timeframe,
            market_stale_threshold_seconds=self._settings.market_stale_threshold_seconds,
        )
        payload["degraded_mode"] = _build_degraded_mode_payload(
            settings=self._settings,
            status_payload=payload,
        )
        return payload

    def shared_contracts_payload(self) -> dict[str, object]:
        """Return the Phase 0 shared contract catalog for cross-surface alignment."""
        return build_shared_contracts_payload(self._settings)

    def inspect_symbol_payload(self, symbol: str) -> dict[str, object]:
        """Inspect one user-entered symbol against Phase 0 layering semantics."""
        raw_input = symbol
        normalized_symbol = symbol.strip().upper()
        format_valid = bool(ASHARE_SYMBOL_PATTERN.fullmatch(normalized_symbol))
        venue = normalized_symbol[-2:] if format_valid else None

        layers = {
            "observed": bool(normalized_symbol),
            "supported": (
                normalized_symbol in self._settings.supported_symbols if format_valid else False
            ),
            "runtime_enabled": (
                normalized_symbol in self._settings.symbols if format_valid else False
            ),
        }
        display_name = (
            self._settings.symbol_names.get(normalized_symbol)
            if format_valid and normalized_symbol in self._settings.symbol_names
            else None
        )
        request_snapshot: RuntimeSymbolRequestSnapshot | None = None
        if format_valid:
            try:
                request_snapshot = self._control_store.get_runtime_symbol_request(
                    account_id=self._settings.account_id,
                    symbol=normalized_symbol,
                )
            except MissingControlPlaneSchemaError:
                request_snapshot = None

        if not format_valid:
            reason_code = "INVALID_SYMBOL_FORMAT"
            message = "代码格式不符合 A 股约定，请使用 6 位数字加 .SH 或 .SZ 后缀。"
            market = "unknown"
            market_label = "待确认"
            venue_label = "待确认"
        elif layers["runtime_enabled"]:
            reason_code = "SYMBOL_RUNTIME_ENABLED"
            message = "该股票代码已进入当前 trader 运行范围，可能影响自动交易判断。"
            market = "a_share"
            market_label = "A 股"
            venue_label = _venue_label(venue)
        elif layers["supported"]:
            reason_code = "SYMBOL_SUPPORTED_NOT_RUNTIME"
            message = "该股票代码已被系统支持，但当前还没有进入 trader 运行范围。"
            market = "a_share"
            market_label = "A 股"
            venue_label = _venue_label(venue)
        else:
            reason_code = "SYMBOL_OBSERVED_ONLY"
            message = "该股票代码当前只处于观察层，可继续校验或纳入后续支持评估。"
            market = "a_share"
            market_label = "A 股"
            venue_label = _venue_label(venue)

        return {
            "raw_input": raw_input,
            "normalized_symbol": normalized_symbol,
            "format_valid": format_valid,
            "market": market,
            "market_label": market_label,
            "venue": venue,
            "venue_label": venue_label,
            "display_name": display_name,
            "name_status": "available" if display_name else "missing",
            "layers": layers,
            "reason_code": reason_code,
            "message": message,
            "runtime_activation": _build_runtime_activation_payload(
                normalized_symbol=normalized_symbol,
                format_valid=format_valid,
                layers=layers,
                request_snapshot=request_snapshot,
                runtime_symbols=self._settings.symbols,
            ),
        }

    def balance_summary_payload(self) -> dict[str, object]:
        try:
            with session_scope(self._session_factory) as session:
                recovery_state = SqlAlchemyRepositories.from_session(
                    session
                ).recovery.load_runtime_state(
                    account_id=self._settings.account_id,
                    event_limit=0,
                )
                latest_balance_snapshots = recovery_state.latest_balance_snapshots
                positions = recovery_state.open_positions
        except Exception as exc:
            if _is_missing_persistence_table_error(exc):
                latest_balance_snapshots = ()
                positions = ()
            else:
                raise

        return _build_balance_summary_payload(
            account_id=self._settings.account_id,
            latest_balance_snapshots=latest_balance_snapshots,
            positions=positions,
        )

    def request_runtime_symbol(
        self,
        *,
        symbol: str,
        confirm: bool,
    ) -> dict[str, object]:
        inspection = self.inspect_symbol_payload(symbol)
        normalized_symbol = str(inspection["normalized_symbol"])
        layers = dict(inspection["layers"])
        runtime_symbols = list(self._settings.symbols)
        requested_runtime_symbols = list(runtime_symbols)
        if (
            normalized_symbol
            and bool(inspection["format_valid"])
            and bool(layers["supported"])
            and normalized_symbol not in requested_runtime_symbols
        ):
            requested_runtime_symbols.append(normalized_symbol)

        status_payload = self._control_store.build_status_view(
            account_id=self._settings.account_id,
            timeframe=self._settings.primary_timeframe,
            market_stale_threshold_seconds=self._settings.market_stale_threshold_seconds,
        )
        response = {
            "accepted": False,
            "symbol": symbol,
            "normalized_symbol": normalized_symbol,
            "control_state": status_payload.get("control_state"),
            "trader_run_id": status_payload.get("trader_run_id"),
            "instance_id": status_payload.get("instance_id"),
            "effective_at": shanghai_now().isoformat(),
            "effective_scope": "runtime_symbols",
            "activation_mode": "requires_reload",
            "request_status": "rejected",
            "message": "",
            "reason_code": "",
            "current_runtime_symbols": runtime_symbols,
            "requested_runtime_symbols": requested_runtime_symbols,
            "last_requested_at": None,
        }

        if not confirm:
            response.update(
                {
                    "request_status": "confirmation_required",
                    "message": "请先确认该变更会影响下一次 trader 运行范围后再提交。",
                    "reason_code": "RUNTIME_REQUEST_CONFIRMATION_REQUIRED",
                }
            )
            return response

        if not bool(inspection["format_valid"]):
            response.update(
                {
                    "request_status": "invalid_symbol",
                    "message": str(inspection["message"]),
                    "reason_code": "INVALID_SYMBOL_FORMAT",
                }
            )
            return response

        if bool(layers["runtime_enabled"]):
            existing_request = self._control_store.get_runtime_symbol_request(
                account_id=self._settings.account_id,
                symbol=normalized_symbol,
            )
            response.update(
                {
                    "accepted": True,
                    "activation_mode": "already_live",
                    "request_status": "already_enabled",
                    "message": "该股票代码已经在当前 runtime 范围内，无需重复申请。",
                    "reason_code": "SYMBOL_RUNTIME_ENABLED",
                    "last_requested_at": (
                        None
                        if existing_request is None or existing_request.requested_at is None
                        else existing_request.requested_at.isoformat()
                    ),
                }
            )
            return response

        if not bool(layers["supported"]):
            response.update(
                {
                    "request_status": "unsupported_symbol",
                    "message": "该股票代码还不在 supported_symbols 范围内，不能直接加入 runtime。",
                    "reason_code": "SYMBOL_NOT_SUPPORTED",
                }
            )
            return response

        existing_request = self._control_store.get_runtime_symbol_request(
            account_id=self._settings.account_id,
            symbol=normalized_symbol,
        )
        if existing_request is not None:
            response.update(
                {
                    "accepted": True,
                    "request_status": existing_request.status,
                    "message": "该股票代码的运行范围变更请求已记录，等待 trader 重载后生效。",
                    "reason_code": "RUNTIME_CHANGE_REQUIRES_RELOAD",
                    "last_requested_at": (
                        None
                        if existing_request.requested_at is None
                        else existing_request.requested_at.isoformat()
                    ),
                }
            )
            return response

        request_snapshot = self._control_store.save_runtime_symbol_request(
            account_id=self._settings.account_id,
            symbol=normalized_symbol,
        )
        response.update(
            {
                "accepted": True,
                "request_status": request_snapshot.status,
                "message": "已记录运行范围变更请求；需要重载 trader 后才会真正进入运行范围。",
                "reason_code": "RUNTIME_CHANGE_REQUIRES_RELOAD",
                "last_requested_at": (
                    None
                    if request_snapshot.requested_at is None
                    else request_snapshot.requested_at.isoformat()
                ),
            }
        )
        return response

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

    def order_history_payload(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        trader_run_id: UUID | None = None,
        account_id: str | None = None,
        symbol: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, object]:
        resolved_account_id = account_id or self._settings.account_id
        normalized_symbol = symbol.strip().upper() if symbol is not None else None
        normalized_status = status.strip().upper() if status is not None else None

        query = (
            select(OrderRecord, OrderIntentRecord)
            .join(OrderIntentRecord, OrderIntentRecord.id == OrderRecord.order_intent_id)
            .where(OrderRecord.account_id == resolved_account_id)
            .order_by(OrderRecord.updated_at.desc(), OrderRecord.id.desc())
        )
        if start_time is not None:
            query = query.where(OrderRecord.updated_at >= start_time)
        if end_time is not None:
            query = query.where(OrderRecord.updated_at <= end_time)
        if trader_run_id is not None:
            query = query.where(OrderRecord.trader_run_id == trader_run_id)
        if normalized_symbol is not None:
            query = query.where(OrderRecord.symbol == normalized_symbol)
        if normalized_status is not None:
            query = query.where(OrderRecord.status == normalized_status)
        query = query.limit(limit)

        try:
            with session_scope(self._session_factory) as session:
                rows = session.execute(query).all()
        except Exception as exc:
            if _is_missing_persistence_table_error(exc):
                rows = ()
            else:
                raise

        return {
            "filters": {
                "start_time": start_time.isoformat() if start_time is not None else None,
                "end_time": end_time.isoformat() if end_time is not None else None,
                "trader_run_id": str(trader_run_id) if trader_run_id is not None else None,
                "account_id": resolved_account_id,
                "symbol": normalized_symbol,
                "status": normalized_status,
                "limit": limit,
            },
            "count": len(rows),
            "orders": [
                {
                    "order_id": order_record.id,
                    "order_intent_id": order_record.order_intent_id,
                    "signal_id": order_intent_record.signal_id,
                    "trader_run_id": order_record.trader_run_id,
                    "account_id": order_record.account_id,
                    "exchange_order_id": order_record.exchange_order_id,
                    "symbol": order_record.symbol,
                    "side": order_record.side,
                    "order_type": order_record.order_type,
                    "time_in_force": order_record.time_in_force,
                    "qty": order_record.qty,
                    "price": order_record.price,
                    "filled_qty": order_record.filled_qty,
                    "avg_fill_price": order_record.avg_fill_price,
                    "status": order_record.status,
                    "reduce_only": order_intent_record.reduce_only,
                    "risk_decision": order_intent_record.risk_decision,
                    "risk_reason": order_intent_record.risk_reason,
                    "submitted_at": order_record.submitted_at.isoformat(),
                    "updated_at": order_record.updated_at.isoformat(),
                    "last_error_code": order_record.last_error_code,
                    "last_error_message": order_record.last_error_message,
                }
                for order_record, order_intent_record in rows
            ],
        }

    def fill_history_payload(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        trader_run_id: UUID | None = None,
        account_id: str | None = None,
        symbol: str | None = None,
        order_id: UUID | None = None,
        limit: int = 50,
    ) -> dict[str, object]:
        resolved_account_id = account_id or self._settings.account_id
        normalized_symbol = symbol.strip().upper() if symbol is not None else None

        query = (
            select(FillRecord, OrderRecord, OrderIntentRecord)
            .join(OrderRecord, OrderRecord.id == FillRecord.order_id)
            .join(OrderIntentRecord, OrderIntentRecord.id == OrderRecord.order_intent_id)
            .where(FillRecord.account_id == resolved_account_id)
            .order_by(FillRecord.fill_time.desc(), FillRecord.id.desc())
        )
        if start_time is not None:
            query = query.where(FillRecord.fill_time >= start_time)
        if end_time is not None:
            query = query.where(FillRecord.fill_time <= end_time)
        if trader_run_id is not None:
            query = query.where(FillRecord.trader_run_id == trader_run_id)
        if normalized_symbol is not None:
            query = query.where(FillRecord.symbol == normalized_symbol)
        if order_id is not None:
            query = query.where(FillRecord.order_id == order_id)
        query = query.limit(limit)

        try:
            with session_scope(self._session_factory) as session:
                rows = session.execute(query).all()
        except Exception as exc:
            if _is_missing_persistence_table_error(exc):
                rows = ()
            else:
                raise

        return {
            "filters": {
                "start_time": start_time.isoformat() if start_time is not None else None,
                "end_time": end_time.isoformat() if end_time is not None else None,
                "trader_run_id": str(trader_run_id) if trader_run_id is not None else None,
                "account_id": resolved_account_id,
                "symbol": normalized_symbol,
                "order_id": str(order_id) if order_id is not None else None,
                "limit": limit,
            },
            "count": len(rows),
            "fills": [
                {
                    "fill_id": fill_record.id,
                    "order_id": fill_record.order_id,
                    "order_intent_id": order_record.order_intent_id,
                    "trader_run_id": fill_record.trader_run_id,
                    "account_id": fill_record.account_id,
                    "exchange_fill_id": fill_record.exchange_fill_id,
                    "symbol": fill_record.symbol,
                    "side": fill_record.side,
                    "qty": fill_record.qty,
                    "price": fill_record.price,
                    "fee": fill_record.fee,
                    "fee_asset": fill_record.fee_asset,
                    "liquidity_type": fill_record.liquidity_type,
                    "fill_time": fill_record.fill_time.isoformat(),
                    "created_at": fill_record.created_at.isoformat(),
                    "reduce_only": order_intent_record.reduce_only,
                }
                for fill_record, order_record, order_intent_record in rows
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

    def market_runtime_bars_payload(
        self,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> dict[str, object]:
        normalized_symbol = self._resolve_symbol(symbol) if symbol is not None else None
        normalized_timeframe = self._resolve_timeframe(timeframe) if timeframe is not None else None

        try:
            runtime_status = self._control_store.load_runtime_status(self._settings.account_id)
        except Exception as exc:
            if _is_missing_persistence_table_error(exc):
                runtime_status = None
            else:
                raise

        last_seen_bars_by_stream = (
            runtime_status.last_seen_bars if runtime_status is not None else {}
        )
        last_strategy_bars_by_stream = (
            runtime_status.last_strategy_bars if runtime_status is not None else {}
        )
        return {
            "filters": {
                "account_id": self._settings.account_id,
                "symbol": normalized_symbol,
                "timeframe": normalized_timeframe,
            },
            "source": "trader_runtime_status",
            "trader_run_id": None if runtime_status is None else runtime_status.trader_run_id,
            "instance_id": None if runtime_status is None else runtime_status.instance_id,
            "lifecycle_status": None if runtime_status is None else runtime_status.lifecycle_status,
            "health_status": None if runtime_status is None else runtime_status.health_status,
            "readiness_status": None if runtime_status is None else runtime_status.readiness_status,
            "updated_at": (
                None if runtime_status is None else runtime_status.updated_at.isoformat()
            ),
            "count": {
                "last_seen": len(
                    _filter_runtime_bar_audit_snapshots(
                        last_seen_bars_by_stream,
                        symbol=normalized_symbol,
                        timeframe=normalized_timeframe,
                    )
                ),
                "last_strategy": len(
                    _filter_runtime_bar_audit_snapshots(
                        last_strategy_bars_by_stream,
                        symbol=normalized_symbol,
                        timeframe=normalized_timeframe,
                    )
                ),
            },
            "available_streams": _build_runtime_stream_summaries(
                last_seen_bars_by_stream=last_seen_bars_by_stream,
                last_strategy_bars_by_stream=last_strategy_bars_by_stream,
            ),
            "last_seen_bars": _filter_runtime_bar_audit_snapshots(
                last_seen_bars_by_stream,
                symbol=normalized_symbol,
                timeframe=normalized_timeframe,
            ),
            "last_strategy_bars": _filter_runtime_bar_audit_snapshots(
                last_strategy_bars_by_stream,
                symbol=normalized_symbol,
                timeframe=normalized_timeframe,
            ),
            "degraded_mode": self.degraded_mode_payload(),
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
        limit: int | None = None,
        mode: ResearchSamplePurpose = "evaluation",
        slippage_model: str = "bar_close_bps",
    ) -> dict[str, object]:
        resolved_symbol = self._resolve_symbol(symbol)
        resolved_timeframe = self._resolve_timeframe(timeframe)
        resolved_limit = resolve_sample_bar_limit(
            sample_purpose=mode,
            requested_limit=limit,
        )
        bars = await self._fetch_historical_bars(
            symbol=resolved_symbol,
            timeframe=resolved_timeframe,
            limit=resolved_limit,
        )
        backtest_bars = _build_research_backtest_bars(bars)
        if not backtest_bars:
            raise LookupError("No finalized bars are available to build a research snapshot yet.")

        runner = build_default_backtest_runner(
            self._settings,
            initial_cash=DEFAULT_RESEARCH_INITIAL_CASH,
            slippage_bps=DEFAULT_RESEARCH_SLIPPAGE_BPS,
            slippage_model=slippage_model,
        )
        result = await runner.run(backtest_bars)
        sample_metadata = build_sample_metadata(
            sample_purpose=mode,
            requested_bar_count=resolved_limit,
            actual_bar_count=len(backtest_bars),
        )

        async def run_segment_backtest(segment_bars) -> object:
            return await build_default_backtest_runner(
                self._settings,
                initial_cash=DEFAULT_RESEARCH_INITIAL_CASH,
                slippage_bps=DEFAULT_RESEARCH_SLIPPAGE_BPS,
                slippage_model=slippage_model,
            ).run(segment_bars)

        segment_analyses = await build_segment_analyses(
            bars=backtest_bars,
            run_backtest=run_segment_backtest,
            sample_purpose=mode,
        )
        notes = [
            "该快照由 `/v1/research/snapshot` 基于真实历史 K 线即时生成。",
            "当前 research 页已直接消费后端回测结果，不再固定停留在本地 fixture 页面。",
            "research snapshot 统一返回 `equityCurve`，仅表示回测权益曲线。",
            (
                "当前 backtest 仍保持整笔成交，不模拟部分成交和成交失败；"
                "剩余执行差异已写入 manifest.executionConstraints。"
            ),
        ]
        if sample_metadata["warning"] is not None:
            notes.append(str(sample_metadata["warning"]))
        if segment_analyses:
            notes.append(
                f"时间分段评估会把样本按时间切成 {len(segment_analyses)} 段，"
                "并在同一起始资金下分别比较阶段表现。"
            )
        return build_web_snapshot_payload(
            result=result,
            bars=backtest_bars,
            source_label="由 research API 生成的真实回测结果",
            source_mode="live",
            notes=tuple(notes),
            sample=sample_metadata,
            segments=segment_analyses,
        )

    def research_ai_settings_payload(self) -> dict[str, object]:
        try:
            snapshot = self._control_store.get_research_ai_settings(self._settings.account_id)
        except MissingControlPlaneSchemaError:
            snapshot = ResearchAiSettingsSnapshot(account_id=self._settings.account_id)
        return _serialize_research_ai_settings(snapshot)

    def save_research_ai_settings(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str | None = None,
        replace_api_key: bool = False,
        clear_api_key: bool = False,
    ) -> dict[str, object]:
        snapshot = self._control_store.save_research_ai_settings(
            account_id=self._settings.account_id,
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            replace_api_key=replace_api_key,
            clear_api_key=clear_api_key,
        )
        return _serialize_research_ai_settings(snapshot)

    async def research_ai_snapshot_payload(
        self,
        *,
        symbol: str | None = None,
        timeframe: str | None = None,
        limit: int = 96,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
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
            raise LookupError(
                "No finalized bars are available to build an AI research snapshot yet."
            )

        strategy = self._build_research_ai_strategy(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        result = await build_default_backtest_runner(
            self._settings,
            strategy=strategy,
            initial_cash=DEFAULT_RESEARCH_INITIAL_CASH,
            slippage_bps=DEFAULT_RESEARCH_SLIPPAGE_BPS,
        ).run(backtest_bars)
        sample_metadata = build_sample_metadata(
            sample_purpose="preview",
            requested_bar_count=limit,
            actual_bar_count=len(backtest_bars),
        )
        notes = [
            (
                "本次 AI 快照通过 OpenAI-compatible Chat Completions 生成，"
                f"模型 {strategy._provider.metadata().get('model', '未指定')}，"
                f"Base URL {strategy._provider.metadata().get('base_url', '未指定')}。"
                if strategy._provider_mode == OPENAI_CHAT_COMPLETIONS
                else "本次 AI 快照使用仓库内置 heuristic stub 生成，不依赖外部模型服务。"
            ),
            "AI 回测优先使用数据库中已保存的模型接入配置，前端临时输入会覆盖本次请求。",
            (
                "AI research snapshot 同样复用了 strategy、order plan、paper "
                "execution 与 portfolio ledger 语义。"
            ),
            "当前 AI backtest 同样默认整笔成交，不额外模拟部分成交和成交失败。",
        ]
        if sample_metadata["warning"] is not None:
            notes.append(str(sample_metadata["warning"]))
        return build_web_snapshot_payload(
            result=result,
            bars=backtest_bars,
            source_label="由 research API 生成的 AI 回测结果",
            source_mode="live",
            notes=notes,
            sample=sample_metadata,
        )

    def _build_research_ai_strategy(
        self,
        *,
        provider: str | None,
        model: str | None,
        base_url: str | None,
        api_key: str | None,
    ) -> AiBarJudgeStrategy:
        config = load_ai_bar_judge_config(AI_BAR_JUDGE_V1)
        try:
            persisted_settings = self._control_store.get_research_ai_settings(
                self._settings.account_id
            )
        except MissingControlPlaneSchemaError:
            persisted_settings = ResearchAiSettingsSnapshot(account_id=self._settings.account_id)
        resolved_provider = (
            provider.strip()
            if provider is not None and provider.strip()
            else persisted_settings.provider
        )
        resolved_model = (
            model.strip() if model is not None and model.strip() else persisted_settings.model
        )
        resolved_base_url = (
            base_url.strip()
            if base_url is not None and base_url.strip()
            else persisted_settings.base_url
        )
        resolved_api_key = (
            api_key.strip()
            if api_key is not None and api_key.strip()
            else persisted_settings.api_key
        )

        if resolved_provider == "heuristic_stub":
            provider_mode = HEURISTIC_STUB
            decision_provider = None
        elif resolved_provider == "openai_compatible":
            provider_mode = OPENAI_CHAT_COMPLETIONS
            decision_provider = OpenAiCompatibleDecisionProvider(
                model=resolved_model,
                base_url=resolved_base_url,
                api_key=resolved_api_key or "",
                entry_threshold_pct=config.entry_threshold_pct,
                exit_threshold_pct=config.exit_threshold_pct,
                timeout_seconds=DEFAULT_AI_RESEARCH_PROVIDER_TIMEOUT_SECONDS,
            )
        else:
            raise ValueError(f"Unsupported AI research provider: {resolved_provider}")

        return AiBarJudgeStrategy(
            account_id=self._settings.account_id,
            strategy_id=config.strategy_id,
            lookback_bars=config.lookback_bars,
            target_position=config.target_position,
            min_confidence=config.min_confidence,
            provider_mode=provider_mode,
            entry_threshold_pct=config.entry_threshold_pct,
            exit_threshold_pct=config.exit_threshold_pct,
            description=config.description,
            provider=decision_provider,
            suppress_provider_errors=False,
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
            effective_scope="strategy_submission",
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
            effective_scope="strategy_submission",
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
            effective_scope="opening_order_gate",
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
            effective_scope="opening_order_gate",
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
            effective_scope="active_orders",
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
            "events": [
                {
                    **event.model_dump(mode="json"),
                    "reason_code": _extract_event_reason_code(event.payload_json),
                }
                for event in events
            ],
            "degraded_mode": self.degraded_mode_payload(),
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
        effective_scope: str,
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
            "effective_scope": effective_scope,
            "message": message,
        }
        if reason_code is not None:
            response["reason_code"] = reason_code
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


def _build_degraded_mode_payload(
    *,
    settings: Settings,
    status_payload: dict[str, object],
) -> dict[str, object]:
    effective_at = str(status_payload.get("as_of") or shanghai_now().isoformat())
    control_state = str(status_payload.get("control_state") or "normal")
    instance_id = status_payload.get("instance_id")
    lease_owner_instance_id = status_payload.get("lease_owner_instance_id")
    trader_run_id = status_payload.get("trader_run_id")
    lifecycle_status = str(status_payload.get("lifecycle_status") or "stopped")
    market_data_fresh = bool(status_payload.get("market_data_fresh"))
    latest_final_bar_time = status_payload.get("latest_final_bar_time")

    if settings.market_data_source == "fixture":
        return {
            "status": "fixture",
            "reason_code": "FIXTURE_DATA_IN_USE",
            "message": "当前系统正在使用 fixture 行情，诊断和价格只适合演练，不应视为真实市场。",
            "data_source": "fixture",
            "effective_at": effective_at,
            "impact": (
                "你看到的价格、runtime audit 和后续判断都基于示例数据，不适合据此判断真实盘中状态。"
            ),
            "suggested_action": "如需确认真实市场状态，请切回 eastmoney 数据源后再查看控制台。",
        }

    if control_state == "protection_mode" or bool(status_payload.get("protection_mode_active")):
        return {
            "status": "degraded",
            "reason_code": "PROTECTION_MODE_ACTIVE",
            "message": "系统当前处于 protection mode，交易动作已经被收紧。",
            "data_source": settings.market_data_source,
            "effective_at": effective_at,
            "impact": (
                "自动交易虽然可能仍在运行，但新的动作会被更保守地限制，不能把系统当成完全正常状态。"
            ),
            "suggested_action": (
                "先查看 replay events 和 runtime bars，"
                "确认是 reconciliation 还是 runtime 健康问题触发了保护模式。"
            ),
        }

    if (
        instance_id is not None
        and lifecycle_status == "running"
        and lease_owner_instance_id != instance_id
    ):
        return {
            "status": "degraded",
            "reason_code": "LEASE_NOT_HELD",
            "message": "当前 trader 不再持有账户 lease，运行状态不能再被当成可安全提交新单。",
            "data_source": settings.market_data_source,
            "effective_at": effective_at,
            "impact": "即使页面还能看到历史状态，也不能假设当前实例仍然拥有提交新订单的资格。",
            "suggested_action": (
                "先确认当前 lease owner，再决定是否需要等待恢复或人工切换运行实例。"
            ),
        }

    if not market_data_fresh:
        if latest_final_bar_time is None:
            return {
                "status": "missing",
                "reason_code": "MARKET_DATA_MISSING",
                "message": "当前还没有拿到可用的最新行情，系统无法确认盘中状态是否可信。",
                "data_source": "missing",
                "effective_at": effective_at,
                "impact": (
                    "页面上的大部分市场相关解释只能基于历史或空状态，不应被当成实时判断依据。"
                ),
                "suggested_action": (
                    "先检查 collector、市场数据源配置和 runtime bar audit，"
                    "确认为什么没有任何最新 bar。"
                ),
            }
        return {
            "status": "degraded",
            "reason_code": "MARKET_DATA_STALE",
            "message": "当前行情存在但已经不新鲜，系统读取到的盘中状态可能落后于真实市场。",
            "data_source": settings.market_data_source,
            "effective_at": effective_at,
            "impact": (
                "你仍然可以查看历史轨迹，但不能把当前价格、权益变化和自动判断当成最新盘中事实。"
            ),
            "suggested_action": (
                "优先查看 runtime bar audit 的最后时间，并确认 collector 是否持续产出 closed bar。"
            ),
        }

    if trader_run_id is None or lifecycle_status != "running":
        return {
            "status": "missing",
            "reason_code": "RUNTIME_STATUS_MISSING",
            "message": "当前还没有活跃 trader runtime 状态，控制台只能显示配置和历史事实。",
            "data_source": "missing",
            "effective_at": effective_at,
            "impact": "当前页面不能证明交易链路正在正常跑，只能说明控制面本身还能访问。",
            "suggested_action": (
                "先确认 trader 进程是否已启动、是否成功绑定 runtime status，并再刷新控制台。"
            ),
        }

    return {
        "status": "normal",
        "reason_code": "LIVE_DATA_READY",
        "message": "当前系统使用真实数据，关键诊断状态没有发现明显降级。",
        "data_source": settings.market_data_source,
        "effective_at": effective_at,
        "impact": "runtime bars、replay events 和控制状态可以作为当前值守判断的主要依据。",
        "suggested_action": "继续按当前控制台查看持仓、订单、事件和 runtime audit 即可。",
    }


def _build_fallback_degraded_mode_payload(
    *,
    settings: Settings,
    effective_at: str,
    message: str | None,
) -> dict[str, object]:
    if message and "missing required tables" in message.lower():
        return {
            "status": "degraded",
            "reason_code": "CONTROL_PLANE_SCHEMA_MISSING",
            "message": (
                "控制面 schema 还没有初始化完成，当前状态只代表服务可访问，不代表诊断事实完整。"
            ),
            "data_source": "unknown",
            "effective_at": effective_at,
            "impact": "很多运行状态、lease 和诊断数据还无法可靠读取，因此页面上的结论不完整。",
            "suggested_action": "先执行数据库 migration，再重新读取控制面状态。",
        }

    return {
        "status": "missing",
        "reason_code": "RUNTIME_STATUS_MISSING",
        "message": message or "当前还没有可用的 runtime 诊断状态。",
        "data_source": ("fixture" if settings.market_data_source == "fixture" else "missing"),
        "effective_at": effective_at,
        "impact": "当前只能看到部分控制面信息，不能据此判断完整的 runtime 健康状态。",
        "suggested_action": "先确认 trader 运行状态和数据源连通性，再重新刷新控制台。",
    }


def _extract_event_reason_code(payload: dict[str, object] | None) -> str | None:
    if not payload:
        return None

    reason_code = payload.get("reason_code")
    if isinstance(reason_code, str) and reason_code.strip():
        return reason_code

    risk_result = payload.get("risk_result")
    if isinstance(risk_result, dict):
        nested_reason_code = risk_result.get("reason_code")
        if isinstance(nested_reason_code, str) and nested_reason_code.strip():
            return nested_reason_code

    diagnostics = payload.get("diagnostics")
    if isinstance(diagnostics, dict):
        nested_reason_code = diagnostics.get("reason_code")
        if isinstance(nested_reason_code, str) and nested_reason_code.strip():
            return nested_reason_code

    return None


def _build_runtime_activation_payload(
    *,
    normalized_symbol: str,
    format_valid: bool,
    layers: dict[str, bool],
    request_snapshot: RuntimeSymbolRequestSnapshot | None,
    runtime_symbols: list[str] | tuple[str, ...],
) -> dict[str, object]:
    requested_runtime_symbols_preview = list(runtime_symbols)
    if (
        format_valid
        and layers["supported"]
        and not layers["runtime_enabled"]
        and normalized_symbol
        and normalized_symbol not in requested_runtime_symbols_preview
    ):
        requested_runtime_symbols_preview.append(normalized_symbol)

    if not format_valid:
        return {
            "requires_confirmation": True,
            "phase": "phase_2_runtime_request",
            "can_apply_now": False,
            "effective_scope": "runtime_symbols",
            "activation_mode": "unavailable",
            "request_status": "invalid_symbol",
            "last_requested_at": None,
            "requested_runtime_symbols_preview": requested_runtime_symbols_preview,
            "message": "代码格式不合法，暂时不能进入 runtime 范围申请。",
        }

    if layers["runtime_enabled"]:
        return {
            "requires_confirmation": True,
            "phase": "phase_2_runtime_request",
            "can_apply_now": False,
            "effective_scope": "runtime_symbols",
            "activation_mode": "already_live",
            "request_status": "already_enabled",
            "last_requested_at": (
                None
                if request_snapshot is None or request_snapshot.requested_at is None
                else request_snapshot.requested_at.isoformat()
            ),
            "requested_runtime_symbols_preview": requested_runtime_symbols_preview,
            "message": "该股票代码已在当前 runtime 范围内，无需再次申请。",
        }

    if request_snapshot is not None:
        return {
            "requires_confirmation": True,
            "phase": "phase_2_runtime_request",
            "can_apply_now": False,
            "effective_scope": "runtime_symbols",
            "activation_mode": request_snapshot.apply_mode,
            "request_status": request_snapshot.status,
            "last_requested_at": (
                None
                if request_snapshot.requested_at is None
                else request_snapshot.requested_at.isoformat()
            ),
            "requested_runtime_symbols_preview": requested_runtime_symbols_preview,
            "message": "该股票代码的运行范围变更请求已记录，等待 trader 重载后生效。",
        }

    if layers["supported"]:
        return {
            "requires_confirmation": True,
            "phase": "phase_2_runtime_request",
            "can_apply_now": True,
            "effective_scope": "runtime_symbols",
            "activation_mode": "requires_reload",
            "request_status": "not_requested",
            "last_requested_at": None,
            "requested_runtime_symbols_preview": requested_runtime_symbols_preview,
            "message": "确认后可以记录运行范围变更请求，但需要重载 trader 才会真正生效。",
        }

    return {
        "requires_confirmation": True,
        "phase": "phase_2_runtime_request",
        "can_apply_now": False,
        "effective_scope": "runtime_symbols",
        "activation_mode": "unavailable",
        "request_status": "unsupported_symbol",
        "last_requested_at": None,
        "requested_runtime_symbols_preview": requested_runtime_symbols_preview,
        "message": "该股票代码尚未进入 supported_symbols，暂时不能申请加入 runtime。",
    }


def _build_balance_summary_payload(
    *,
    account_id: str,
    latest_balance_snapshots: tuple[BalanceSnapshot, ...],
    positions: tuple[Position, ...],
) -> dict[str, object]:
    latest_cash_snapshot = next(
        (snapshot for snapshot in latest_balance_snapshots if snapshot.asset == "CNY"),
        None,
    )
    cash_balance = Decimal("0") if latest_cash_snapshot is None else latest_cash_snapshot.total
    available_cash = (
        Decimal("0") if latest_cash_snapshot is None else latest_cash_snapshot.available
    )
    frozen_cash = Decimal("0") if latest_cash_snapshot is None else latest_cash_snapshot.locked

    market_value = Decimal("0")
    unrealized_pnl = Decimal("0")
    realized_pnl = Decimal("0")
    fallback_mark_count = 0
    latest_position_time: datetime | None = None
    for position in positions:
        if latest_position_time is None or position.updated_at > latest_position_time:
            latest_position_time = position.updated_at
        mark_price = position.mark_price or position.avg_entry_price
        if position.mark_price is None and mark_price is not None:
            fallback_mark_count += 1
        if mark_price is not None:
            market_value += position.qty * mark_price
        unrealized_pnl += position.unrealized_pnl
        realized_pnl += position.realized_pnl

    equity = cash_balance + market_value
    cash_as_of_time = None if latest_cash_snapshot is None else latest_cash_snapshot.snapshot_time
    as_of_time = max(
        (
            candidate
            for candidate in (cash_as_of_time, latest_position_time)
            if candidate is not None
        ),
        default=None,
    )

    if latest_cash_snapshot is None and not positions:
        summary_message = "当前还没有账户资金快照，暂时无法解释现金、持仓和权益之间的关系。"
    elif latest_cash_snapshot is None:
        summary_message = (
            "当前缺少最新现金快照，下面的权益只按持仓估值近似展示，不建议据此判断真实可用资金。"
        )
    elif not positions:
        summary_message = (
            "当前没有持仓，账户权益等于现金余额；可用资金和冻结资金已经直接体现在现金拆分里。"
        )
    else:
        summary_message = (
            "当前账户权益由现金余额和持仓市值共同组成；"
            "可用资金可以继续下单，冻结资金说明还有资金被订单占用。"
        )

    cash_explanation = (
        "现金余额 = 可用资金 + 冻结资金。可用资金还能继续下单，冻结资金通常表示仍有订单占用资金。"
        if latest_cash_snapshot is not None
        else "现金快照暂缺，因此当前还不能准确解释可用资金和冻结资金。"
    )
    position_explanation = (
        "持仓市值按当前持仓数量乘以最新标记价格估算。"
        if fallback_mark_count == 0
        else "部分持仓缺少最新标记价格时，会暂时回退到成本价估算持仓市值。"
    )
    equity_explanation = (
        "账户权益 = 现金余额 + 持仓市值。"
        "未实现盈亏来自持仓价格波动，已实现盈亏来自已经完成的买卖结果。"
    )

    return {
        "account_id": account_id,
        "cash_balance": _decimal_to_string(cash_balance),
        "available_cash": _decimal_to_string(available_cash),
        "frozen_cash": _decimal_to_string(frozen_cash),
        "market_value": _decimal_to_string(market_value),
        "equity": _decimal_to_string(equity),
        "unrealized_pnl": _decimal_to_string(unrealized_pnl),
        "realized_pnl": _decimal_to_string(realized_pnl),
        "position_count": len(positions),
        "cash_as_of_time": None if cash_as_of_time is None else cash_as_of_time.isoformat(),
        "positions_as_of_time": (
            None if latest_position_time is None else latest_position_time.isoformat()
        ),
        "as_of_time": None if as_of_time is None else as_of_time.isoformat(),
        "summary_message": summary_message,
        "cash_explanation": cash_explanation,
        "position_explanation": position_explanation,
        "equity_explanation": equity_explanation,
    }


def _decimal_to_string(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


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


def _venue_label(venue: str | None) -> str:
    if venue == "SH":
        return "上海证券交易所"
    if venue == "SZ":
        return "深圳证券交易所"
    return "待确认"


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


def _filter_runtime_bar_audit_snapshots(
    snapshots_by_stream: dict[str, dict[str, object]],
    *,
    symbol: str | None,
    timeframe: str | None,
) -> list[dict[str, object]]:
    filtered = [
        dict(snapshot)
        for snapshot in snapshots_by_stream.values()
        if (symbol is None or snapshot.get("symbol") == symbol)
        and (timeframe is None or snapshot.get("timeframe") == timeframe)
    ]
    return sorted(
        filtered,
        key=lambda snapshot: (
            str(snapshot.get("event_time") or ""),
            str(snapshot.get("stream_key") or ""),
        ),
        reverse=True,
    )


def _build_runtime_stream_summaries(
    *,
    last_seen_bars_by_stream: dict[str, dict[str, object]],
    last_strategy_bars_by_stream: dict[str, dict[str, object]],
) -> list[dict[str, Any]]:
    stream_keys = set(last_seen_bars_by_stream) | set(last_strategy_bars_by_stream)
    summaries: list[dict[str, Any]] = []
    for stream_key in stream_keys:
        seen_snapshot = last_seen_bars_by_stream.get(stream_key)
        strategy_snapshot = last_strategy_bars_by_stream.get(stream_key)
        anchor_snapshot = seen_snapshot or strategy_snapshot or {}
        summaries.append(
            {
                "stream_key": stream_key,
                "symbol": anchor_snapshot.get("symbol"),
                "timeframe": anchor_snapshot.get("timeframe"),
                "exchange": anchor_snapshot.get("exchange"),
                "last_seen_event_time": (
                    None if seen_snapshot is None else seen_snapshot.get("event_time")
                ),
                "last_strategy_event_time": (
                    None if strategy_snapshot is None else strategy_snapshot.get("event_time")
                ),
            }
        )
    return sorted(
        summaries,
        key=lambda summary: (
            str(
                summary.get("last_seen_event_time") or summary.get("last_strategy_event_time") or ""
            ),
            str(summary.get("stream_key") or ""),
        ),
        reverse=True,
    )


def _serialize_research_ai_settings(snapshot: ResearchAiSettingsSnapshot) -> dict[str, object]:
    return {
        "accountId": snapshot.account_id,
        "provider": snapshot.provider,
        "model": snapshot.model,
        "baseUrl": snapshot.base_url,
        "hasApiKey": snapshot.has_api_key,
        "apiKeyHint": _mask_api_key(snapshot.api_key),
        "updatedAt": None if snapshot.updated_at is None else snapshot.updated_at.isoformat(),
    }


def _mask_api_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) <= 8:
        return "*" * len(normalized)
    return f"{normalized[:3]}...{normalized[-4:]}"
