"""Minimal control-plane service used by the Phase 6B API."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import sessionmaker
from src.config import Settings
from src.domain.events import BarEvent
from src.domain.execution import OrderSide, OrderStatus
from src.domain.market import NormalizedBar
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
    TraderControlPlaneStore,
)
from apps.trader.oms import build_default_trader_oms_service
from apps.trader.reconciliation import SessionFactoryBackedReconciliationStore

READ_ONLY_MARKET_TIMEFRAMES = frozenset({"15m", "1h"})
DEFAULT_RESEARCH_INITIAL_CASH = Decimal("100000")
DEFAULT_RESEARCH_SLIPPAGE_BPS = Decimal("5")
DEFAULT_AI_RESEARCH_PROVIDER_TIMEOUT_SECONDS = 30.0


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
        return {
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
            return self._default_status_payload(message=str(exc))

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
        ]
        if sample_metadata["warning"] is not None:
            notes.append(str(sample_metadata["warning"]))
        if segment_analyses:
            notes.append(
                f"时间分段评估会把样本按时间切成 {len(segment_analyses)} 段，并在同一起始资金下分别比较阶段表现。"
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
                summary.get("last_seen_event_time")
                or summary.get("last_strategy_event_time")
                or ""
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
