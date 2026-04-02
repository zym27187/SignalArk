from __future__ import annotations

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from apps.mcp.server import SignalArkMcpBackend, SignalArkMcpServer
from sqlalchemy.orm import sessionmaker
from src.config import Settings
from src.infra.db import create_database_engine, create_session_factory, session_scope
from src.infra.db.base import Base
from src.infra.db.models import FillRecord, OrderIntentRecord, OrderRecord, SignalRecord
from src.shared.types import SHANGHAI_TIMEZONE


class StubControlPlaneService:
    def status_payload(self) -> dict[str, object]:
        return {"status": "ready", "account_id": "paper_account_001", "ready": True}

    def positions_payload(self) -> dict[str, object]:
        return {"account_id": "paper_account_001", "positions": []}

    def active_orders_payload(self) -> dict[str, object]:
        return {"account_id": "paper_account_001", "orders": []}

    def replay_events_payload(self, **_: object) -> dict[str, object]:
        return {"filters": {}, "count": 0, "events": []}

    async def market_bars_payload(self, **_: object) -> dict[str, object]:
        return {"symbol": "600036.SH", "timeframe": "15m", "count": 1, "bars": []}

    async def research_snapshot_payload(self, **_: object) -> dict[str, object]:
        return {"sourceMode": "live", "manifest": {"symbols": ["600036.SH"]}}


def _make_backend(
    tmp_path: Path,
    *,
    create_tables: bool,
    service: StubControlPlaneService | None = None,
) -> SignalArkMcpBackend:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'signalark_mcp.sqlite3'}"
    settings = Settings(postgres_dsn=database_url)
    engine = create_database_engine(settings=settings)
    if create_tables:
        Base.metadata.create_all(bind=engine)
    session_factory = create_session_factory(engine)
    return SignalArkMcpBackend(
        settings=settings,
        session_factory=session_factory,
        control_plane_service=service or StubControlPlaneService(),
    )


def _decode_tool_payload(result: dict[str, object]) -> dict[str, object]:
    content = result["content"]
    assert isinstance(content, list)
    text_item = content[0]
    assert isinstance(text_item, dict)
    return json.loads(text_item["text"])


def test_signalark_mcp_server_initializes_and_lists_tools(tmp_path: Path) -> None:
    server = SignalArkMcpServer(_make_backend(tmp_path, create_tables=False))

    initialize_response = asyncio.run(
        server._handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25"},
            }
        )
    )

    assert initialize_response is not None
    assert initialize_response["result"]["serverInfo"]["name"] == "signalark-mcp"

    tools_response = asyncio.run(
        server._handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            }
        )
    )

    assert tools_response is not None
    names = [tool["name"] for tool in tools_response["result"]["tools"]]
    assert "list_order_history" in names
    assert "run_research_snapshot" in names


def test_signalark_mcp_server_allows_ping_before_initialize(tmp_path: Path) -> None:
    server = SignalArkMcpServer(_make_backend(tmp_path, create_tables=False))

    response = asyncio.run(
        server._handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "ping",
                "params": {},
            }
        )
    )

    assert response == {"jsonrpc": "2.0", "id": 1, "result": {}}


def test_history_tools_return_empty_payloads_when_tables_are_missing(tmp_path: Path) -> None:
    backend = _make_backend(tmp_path, create_tables=False)

    order_result = asyncio.run(backend.call_tool("list_order_history", {"limit": 10}))
    fill_result = asyncio.run(backend.call_tool("list_fill_history", {"limit": 10}))

    assert order_result["isError"] is False
    assert fill_result["isError"] is False
    assert _decode_tool_payload(order_result)["count"] == 0
    assert _decode_tool_payload(fill_result)["count"] == 0


def test_history_tools_return_persisted_orders_and_fills(tmp_path: Path) -> None:
    backend = _make_backend(tmp_path, create_tables=True)
    _insert_sample_execution_chain(backend._session_factory)

    order_result = asyncio.run(backend.call_tool("list_order_history", {"limit": 10}))
    fill_result = asyncio.run(backend.call_tool("list_fill_history", {"limit": 10}))

    decoded_orders = _decode_tool_payload(order_result)
    decoded_fills = _decode_tool_payload(fill_result)

    assert decoded_orders["count"] == 1
    assert decoded_orders["orders"][0]["status"] == "FILLED"
    assert decoded_orders["orders"][0]["reduce_only"] is False
    assert decoded_orders["orders"][0]["qty"] == "200.0000000000"

    assert decoded_fills["count"] == 1
    assert decoded_fills["fills"][0]["symbol"] == "600036.SH"
    assert decoded_fills["fills"][0]["fee"] == "1.2300000000"


def test_market_and_research_tools_delegate_to_control_plane_service(tmp_path: Path) -> None:
    backend = _make_backend(tmp_path, create_tables=False, service=StubControlPlaneService())

    market_result = asyncio.run(
        backend.call_tool("get_market_bars", {"symbol": "600036.SH", "limit": 1})
    )
    research_result = asyncio.run(
        backend.call_tool("run_research_snapshot", {"symbol": "600036.SH", "limit": 10})
    )

    assert market_result["isError"] is False
    assert research_result["isError"] is False
    assert _decode_tool_payload(market_result)["count"] == 1
    assert _decode_tool_payload(research_result)["sourceMode"] == "live"


def _insert_sample_execution_chain(session_factory: sessionmaker) -> None:
    signal_id = uuid4()
    order_intent_id = uuid4()
    order_id = uuid4()
    fill_id = uuid4()
    trader_run_id = uuid4()
    timestamp = datetime(2026, 4, 3, 10, 15, tzinfo=SHANGHAI_TIMEZONE)

    with session_scope(session_factory) as session:
        session.add(
            SignalRecord(
                id=signal_id,
                strategy_id="baseline_momentum_v1",
                trader_run_id=trader_run_id,
                account_id="paper_account_001",
                exchange="cn_equity",
                symbol="600036.SH",
                timeframe="15m",
                signal_type="TARGET_POSITION",
                target_position=Decimal("1"),
                confidence=Decimal("0.88"),
                reason_summary="momentum breakout",
                status="NEW",
                event_time=timestamp,
                created_at=timestamp,
            )
        )
        session.add(
            OrderIntentRecord(
                id=order_intent_id,
                signal_id=signal_id,
                strategy_id="baseline_momentum_v1",
                trader_run_id=trader_run_id,
                account_id="paper_account_001",
                exchange="cn_equity",
                symbol="600036.SH",
                side="BUY",
                order_type="LIMIT",
                time_in_force="DAY",
                qty=Decimal("200"),
                price=Decimal("42.10"),
                decision_price=Decimal("42.00"),
                reduce_only=False,
                market_context_json={"phase": "continuous"},
                idempotency_key="intent-001",
                status="SUBMITTED",
                risk_decision="ALLOW",
                risk_reason=None,
                created_at=timestamp,
            )
        )
        session.add(
            OrderRecord(
                id=order_id,
                order_intent_id=order_intent_id,
                trader_run_id=trader_run_id,
                exchange_order_id="paper-order-001",
                account_id="paper_account_001",
                exchange="cn_equity",
                symbol="600036.SH",
                side="BUY",
                order_type="LIMIT",
                time_in_force="DAY",
                qty=Decimal("200"),
                price=Decimal("42.10"),
                filled_qty=Decimal("200"),
                avg_fill_price=Decimal("42.08"),
                status="FILLED",
                last_error_code=None,
                last_error_message=None,
                submitted_at=timestamp,
                updated_at=timestamp,
            )
        )
        session.add(
            FillRecord(
                id=fill_id,
                order_id=order_id,
                trader_run_id=trader_run_id,
                exchange_fill_id="paper-fill-001",
                account_id="paper_account_001",
                exchange="cn_equity",
                symbol="600036.SH",
                side="BUY",
                qty=Decimal("200"),
                price=Decimal("42.08"),
                fee=Decimal("1.23"),
                fee_asset="CNY",
                liquidity_type="MAKER",
                fill_time=timestamp,
                created_at=timestamp,
            )
        )
