"""Minimal stdio MCP server for SignalArk diagnostics and research workflows."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

import httpx
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import Select, select
from sqlalchemy.orm import sessionmaker
from src.config import Settings, load_settings
from src.infra.db import create_database_engine, create_session_factory, session_scope
from src.infra.db.models import FillRecord, OrderIntentRecord, OrderRecord
from src.infra.observability import SignalArkObservability

from apps.api.control_plane import ApiControlPlaneService, _is_missing_persistence_table_error
from apps.trader.control_plane import TraderControlPlaneStore

SERVER_NAME = "signalark-mcp"
SERVER_VERSION = "0.1.0"
JSONRPC_VERSION = "2.0"
SUPPORTED_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
)
DEFAULT_ORDER_HISTORY_LIMIT = 50
DEFAULT_FILL_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 200
MAX_REPLAY_LIMIT = 500


class NoArguments(BaseModel):
    """Empty object schema for tools without input arguments."""

    model_config = ConfigDict(extra="forbid")


class BaseToolArguments(BaseModel):
    """Base model that forbids unknown MCP tool arguments."""

    model_config = ConfigDict(extra="forbid")


class OrderHistoryArguments(BaseToolArguments):
    """Filtering options for historical order lookups."""

    account_id: str | None = None
    symbol: str | None = None
    status: str | None = None
    trader_run_id: UUID | None = None
    limit: int = Field(default=DEFAULT_ORDER_HISTORY_LIMIT, ge=1, le=MAX_HISTORY_LIMIT)


class FillHistoryArguments(BaseToolArguments):
    """Filtering options for historical fill lookups."""

    account_id: str | None = None
    symbol: str | None = None
    trader_run_id: UUID | None = None
    order_id: UUID | None = None
    limit: int = Field(default=DEFAULT_FILL_HISTORY_LIMIT, ge=1, le=MAX_HISTORY_LIMIT)


class ReplayEventsArguments(BaseToolArguments):
    """Filtering options for replaying persisted audit events."""

    start_time: datetime | None = None
    end_time: datetime | None = None
    trader_run_id: UUID | None = None
    account_id: str | None = None
    symbol: str | None = None
    limit: int = Field(default=100, ge=1, le=MAX_REPLAY_LIMIT)


class MarketReadArguments(BaseToolArguments):
    """Common arguments for read-only market and research snapshots."""

    symbol: str | None = None
    timeframe: str | None = None
    limit: int = Field(default=96, ge=1, le=200)


ToolHandler = Callable[[BaseModel], dict[str, object] | Awaitable[dict[str, object]]]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Static MCP tool metadata plus a typed handler."""

    name: str
    description: str
    arguments_model: type[BaseModel]
    handler: ToolHandler

    def as_mcp_tool(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.arguments_model.model_json_schema(),
        }


class SignalArkMcpBackend:
    """Dispatch read-only SignalArk MCP tools against local services and persistence."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker,
        control_plane_service: ApiControlPlaneService,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._control_plane_service = control_plane_service
        self._tools = {
            definition.name: definition
            for definition in (
                ToolDefinition(
                    name="get_status",
                    description="Return the current trader status, readiness, and control state.",
                    arguments_model=NoArguments,
                    handler=self._get_status,
                ),
                ToolDefinition(
                    name="list_positions",
                    description=(
                        "Return the current persisted positions for the configured account."
                    ),
                    arguments_model=NoArguments,
                    handler=self._list_positions,
                ),
                ToolDefinition(
                    name="list_active_orders",
                    description="Return currently active orders for the configured account.",
                    arguments_model=NoArguments,
                    handler=self._list_active_orders,
                ),
                ToolDefinition(
                    name="list_order_history",
                    description=(
                        "Return persisted order history, optionally filtered by symbol, status, "
                        "or trader run."
                    ),
                    arguments_model=OrderHistoryArguments,
                    handler=self._list_order_history,
                ),
                ToolDefinition(
                    name="list_fill_history",
                    description=(
                        "Return persisted fill history, optionally filtered by symbol, order, "
                        "or trader run."
                    ),
                    arguments_model=FillHistoryArguments,
                    handler=self._list_fill_history,
                ),
                ToolDefinition(
                    name="replay_events",
                    description="Replay persisted audit events with optional filters.",
                    arguments_model=ReplayEventsArguments,
                    handler=self._replay_events,
                ),
                ToolDefinition(
                    name="get_market_bars",
                    description=(
                        "Fetch read-only historical bars via the configured market gateway."
                    ),
                    arguments_model=MarketReadArguments,
                    handler=self._get_market_bars,
                ),
                ToolDefinition(
                    name="run_research_snapshot",
                    description=(
                        "Run the existing research snapshot flow against recent historical bars "
                        "and return the frontend-aligned payload."
                    ),
                    arguments_model=MarketReadArguments,
                    handler=self._run_research_snapshot,
                ),
            )
        }

    @classmethod
    def from_settings(cls, settings: Settings) -> SignalArkMcpBackend:
        engine = create_database_engine(settings=settings)
        session_factory = create_session_factory(engine)
        control_store = TraderControlPlaneStore(session_factory)
        service = ApiControlPlaneService(
            settings=settings,
            session_factory=session_factory,
            control_store=control_store,
            observability=SignalArkObservability(
                service="mcp",
                logger_name="signalark.mcp.observability",
            ),
        )
        return cls(
            settings=settings,
            session_factory=session_factory,
            control_plane_service=service,
        )

    def list_tools(self) -> list[dict[str, object]]:
        return [definition.as_mcp_tool() for definition in self._tools.values()]

    async def call_tool(self, name: str, arguments: dict[str, object] | None) -> dict[str, object]:
        definition = self._tools.get(name)
        if definition is None:
            raise JsonRpcError(code=-32602, message=f"Unknown tool: {name}")

        try:
            parsed_arguments = definition.arguments_model.model_validate(arguments or {})
        except ValidationError as exc:
            raise JsonRpcError(
                code=-32602,
                message=f"Invalid arguments for tool {name}",
                data=exc.errors(),
            ) from exc

        try:
            payload = definition.handler(parsed_arguments)
            if asyncio.iscoroutine(payload):
                payload = await payload
        except httpx.HTTPError as exc:
            return _tool_error_result(
                f"Upstream market data request failed while running `{name}`: {exc}"
            )
        except ValueError as exc:
            return _tool_error_result(str(exc))
        except Exception as exc:
            return _tool_error_result(
                f"Unexpected SignalArk error while running `{name}`: {exc}"
            )

        return _tool_success_result(payload)

    def _get_status(self, _: NoArguments) -> dict[str, object]:
        return self._control_plane_service.status_payload()

    def _list_positions(self, _: NoArguments) -> dict[str, object]:
        return self._control_plane_service.positions_payload()

    def _list_active_orders(self, _: NoArguments) -> dict[str, object]:
        return self._control_plane_service.active_orders_payload()

    def _list_order_history(self, args: OrderHistoryArguments) -> dict[str, object]:
        account_id = args.account_id or self._settings.account_id
        query: Select[tuple[OrderRecord, OrderIntentRecord]] = (
            select(OrderRecord, OrderIntentRecord)
            .join(OrderIntentRecord, OrderIntentRecord.id == OrderRecord.order_intent_id)
            .where(OrderRecord.account_id == account_id)
            .order_by(OrderRecord.updated_at.desc(), OrderRecord.id.desc())
        )
        if args.symbol is not None:
            query = query.where(OrderRecord.symbol == args.symbol.strip().upper())
        if args.status is not None:
            query = query.where(OrderRecord.status == args.status.strip().upper())
        if args.trader_run_id is not None:
            query = query.where(OrderRecord.trader_run_id == args.trader_run_id)
        query = query.limit(args.limit)

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
                "account_id": account_id,
                "symbol": args.symbol.strip().upper() if args.symbol is not None else None,
                "status": args.status.strip().upper() if args.status is not None else None,
                "trader_run_id": str(args.trader_run_id) if args.trader_run_id else None,
                "limit": args.limit,
            },
            "count": len(rows),
            "orders": [
                {
                    "order_id": order.id,
                    "order_intent_id": order.order_intent_id,
                    "signal_id": intent.signal_id,
                    "trader_run_id": order.trader_run_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "order_type": order.order_type,
                    "time_in_force": order.time_in_force,
                    "qty": order.qty,
                    "filled_qty": order.filled_qty,
                    "avg_fill_price": order.avg_fill_price,
                    "status": order.status,
                    "reduce_only": intent.reduce_only,
                    "risk_decision": intent.risk_decision,
                    "risk_reason": intent.risk_reason,
                    "submitted_at": order.submitted_at.isoformat(),
                    "updated_at": order.updated_at.isoformat(),
                    "last_error_code": order.last_error_code,
                    "last_error_message": order.last_error_message,
                }
                for order, intent in rows
            ],
        }

    def _list_fill_history(self, args: FillHistoryArguments) -> dict[str, object]:
        account_id = args.account_id or self._settings.account_id
        query: Select[tuple[FillRecord, OrderRecord, OrderIntentRecord]] = (
            select(FillRecord, OrderRecord, OrderIntentRecord)
            .join(OrderRecord, OrderRecord.id == FillRecord.order_id)
            .join(OrderIntentRecord, OrderIntentRecord.id == OrderRecord.order_intent_id)
            .where(FillRecord.account_id == account_id)
            .order_by(FillRecord.fill_time.desc(), FillRecord.id.desc())
        )
        if args.symbol is not None:
            query = query.where(FillRecord.symbol == args.symbol.strip().upper())
        if args.trader_run_id is not None:
            query = query.where(FillRecord.trader_run_id == args.trader_run_id)
        if args.order_id is not None:
            query = query.where(FillRecord.order_id == args.order_id)
        query = query.limit(args.limit)

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
                "account_id": account_id,
                "symbol": args.symbol.strip().upper() if args.symbol is not None else None,
                "trader_run_id": str(args.trader_run_id) if args.trader_run_id else None,
                "order_id": str(args.order_id) if args.order_id else None,
                "limit": args.limit,
            },
            "count": len(rows),
            "fills": [
                {
                    "fill_id": fill.id,
                    "order_id": fill.order_id,
                    "order_intent_id": order.order_intent_id,
                    "trader_run_id": fill.trader_run_id,
                    "symbol": fill.symbol,
                    "side": fill.side,
                    "qty": fill.qty,
                    "price": fill.price,
                    "fee": fill.fee,
                    "fee_asset": fill.fee_asset,
                    "liquidity_type": fill.liquidity_type,
                    "fill_time": fill.fill_time.isoformat(),
                    "created_at": fill.created_at.isoformat(),
                    "reduce_only": intent.reduce_only,
                }
                for fill, order, intent in rows
            ],
        }

    def _replay_events(self, args: ReplayEventsArguments) -> dict[str, object]:
        return self._control_plane_service.replay_events_payload(
            start_time=args.start_time,
            end_time=args.end_time,
            trader_run_id=args.trader_run_id,
            account_id=args.account_id,
            symbol=args.symbol.strip().upper() if args.symbol is not None else None,
            limit=args.limit,
        )

    async def _get_market_bars(self, args: MarketReadArguments) -> dict[str, object]:
        return await self._control_plane_service.market_bars_payload(
            symbol=args.symbol,
            timeframe=args.timeframe,
            limit=args.limit,
        )

    async def _run_research_snapshot(self, args: MarketReadArguments) -> dict[str, object]:
        return await self._control_plane_service.research_snapshot_payload(
            symbol=args.symbol,
            timeframe=args.timeframe,
            limit=args.limit,
        )


class JsonRpcError(Exception):
    """Structured JSON-RPC error raised during request dispatch."""

    def __init__(
        self,
        *,
        code: int,
        message: str,
        data: object | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class SignalArkMcpServer:
    """Small MCP stdio server that implements only the tools needed for SignalArk V1."""

    def __init__(self, backend: SignalArkMcpBackend) -> None:
        self._backend = backend
        self._initialized = False
        self._protocol_version = SUPPORTED_PROTOCOL_VERSIONS[0]

    def serve_forever(self) -> None:
        while True:
            raw_message = sys.stdin.buffer.readline()
            if raw_message == b"":
                return

            message = raw_message.decode("utf-8").strip()
            if not message:
                continue

            try:
                payload = json.loads(message)
            except json.JSONDecodeError as exc:
                self._write_message(
                    _json_rpc_error_response(
                        request_id=None,
                        code=-32700,
                        message=f"Parse error: {exc.msg}",
                    )
                )
                continue

            responses = asyncio.run(self._handle_envelope(payload))
            for response in responses:
                self._write_message(response)

    async def _handle_envelope(self, payload: object) -> list[dict[str, object]]:
        if isinstance(payload, list):
            if not payload:
                return [
                    _json_rpc_error_response(
                        request_id=None,
                        code=-32600,
                        message="Invalid Request",
                    )
                ]
            responses: list[dict[str, object]] = []
            for item in payload:
                response = await self._handle_message(item)
                if response is not None:
                    responses.append(response)
            return responses

        response = await self._handle_message(payload)
        return [] if response is None else [response]

    async def _handle_message(self, payload: object) -> dict[str, object] | None:
        if not isinstance(payload, dict):
            return _json_rpc_error_response(
                request_id=None,
                code=-32600,
                message="Invalid Request",
            )

        method = payload.get("method")
        params = payload.get("params")
        request_id = payload.get("id")

        if not isinstance(method, str):
            if request_id is None:
                return None
            return _json_rpc_error_response(
                request_id=request_id,
                code=-32600,
                message="Invalid Request",
            )

        if method == "notifications/initialized":
            self._initialized = True
            return None
        if method.startswith("notifications/"):
            return None

        if method not in {"initialize", "ping"} and not self._initialized:
            if request_id is None:
                return None
            return _json_rpc_error_response(
                request_id=request_id,
                code=-32002,
                message="Server not initialized",
            )

        try:
            result = await self._dispatch_request(method=method, params=params)
        except JsonRpcError as exc:
            if request_id is None:
                return None
            return _json_rpc_error_response(
                request_id=request_id,
                code=exc.code,
                message=exc.message,
                data=exc.data,
            )

        if request_id is None:
            return None

        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "result": result,
        }

    async def _dispatch_request(self, *, method: str, params: object) -> dict[str, object]:
        if params is not None and not isinstance(params, dict):
            raise JsonRpcError(code=-32602, message="Request params must be a JSON object")

        normalized_params = params or {}

        if method == "initialize":
            self._initialized = True
            requested_version = normalized_params.get("protocolVersion")
            if (
                isinstance(requested_version, str)
                and requested_version in SUPPORTED_PROTOCOL_VERSIONS
            ):
                self._protocol_version = requested_version
            return {
                "protocolVersion": self._protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
                "instructions": (
                    "Read-only SignalArk diagnostics and research server. "
                    "Use it to inspect status, history, events, bars, and research snapshots."
                ),
            }

        if method == "ping":
            return {}

        if method == "tools/list":
            return {"tools": self._backend.list_tools()}

        if method == "tools/call":
            name = normalized_params.get("name")
            arguments = normalized_params.get("arguments")
            if not isinstance(name, str) or not name.strip():
                raise JsonRpcError(code=-32602, message="tools/call requires a non-empty name")
            if arguments is not None and not isinstance(arguments, dict):
                raise JsonRpcError(
                    code=-32602,
                    message="tools/call arguments must be a JSON object when provided",
                )
            return await self._backend.call_tool(name=name, arguments=arguments)

        raise JsonRpcError(code=-32601, message=f"Method not found: {method}")

    @staticmethod
    def _write_message(payload: dict[str, object]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        sys.stdout.write(serialized)
        sys.stdout.write("\n")
        sys.stdout.flush()


def _tool_success_result(payload: dict[str, object]) -> dict[str, object]:
    encoded_payload = jsonable_encoder(
        payload,
        custom_encoder={
            UUID: str,
            Decimal: str,
        },
    )
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(encoded_payload, ensure_ascii=False, indent=2),
            }
        ],
        "isError": False,
    }


def _tool_error_result(message: str) -> dict[str, object]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


def _json_rpc_error_response(
    *,
    request_id: object | None,
    code: int,
    message: str,
    data: object | None = None,
) -> dict[str, object]:
    error: dict[str, object] = {
        "code": code,
        "message": message,
    }
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": error,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config-profile",
        help="Optional config profile to load before env overrides.",
    )
    parser.add_argument(
        "--config-file",
        help="Optional extra YAML config file layered on top of the selected profile.",
    )
    parser.add_argument(
        "--postgres-dsn",
        help=(
            "Optional runtime DSN override. When set, it is exported to "
            "SIGNALARK_POSTGRES_DSN before settings are loaded."
        ),
    )
    return parser


def _load_cli_settings(args: argparse.Namespace) -> Settings:
    if args.postgres_dsn:
        os.environ["SIGNALARK_POSTGRES_DSN"] = args.postgres_dsn
    return load_settings(
        config_profile=args.config_profile,
        config_file=args.config_file,
    )


def main() -> None:
    args = _build_parser().parse_args()
    settings = _load_cli_settings(args)
    backend = SignalArkMcpBackend.from_settings(settings)
    SignalArkMcpServer(backend).serve_forever()
