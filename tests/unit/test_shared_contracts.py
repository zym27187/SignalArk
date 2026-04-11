from __future__ import annotations

from src.config import Settings
from src.config.shared_contracts import (
    V2_SHARED_CONTRACT_VERSION,
    build_shared_contracts_payload,
)


def test_shared_contract_catalog_exposes_phase_0_symbol_layers() -> None:
    settings = Settings(
        postgres_dsn="sqlite+pysqlite:///:memory:",
        supported_symbols=["600036.SH", "000001.SZ"],
        symbol_names={
            "600036.SH": "CMB",
            "000001.SZ": "PINGAN",
        },
        symbols=["600036.SH"],
    )

    payload = build_shared_contracts_payload(settings)

    assert payload["contract_version"] == V2_SHARED_CONTRACT_VERSION
    assert payload["phase"] == "phase_0"

    symbol_layer_contract = payload["symbol_layer_contract"]
    assert symbol_layer_contract["layer_order"] == [
        "observed",
        "supported",
        "runtime_enabled",
    ]
    assert symbol_layer_contract["current_boundaries"] == {
        "supported_symbols": ["600036.SH", "000001.SZ"],
        "runtime_symbols": ["600036.SH"],
        "runtime_subset_of_supported": True,
    }

    supported_entries = symbol_layer_contract["current_supported_entries"]
    assert supported_entries[0]["symbol"] == "600036.SH"
    assert supported_entries[0]["layers"] == {
        "observed": True,
        "supported": True,
        "runtime_enabled": True,
    }
    assert supported_entries[0]["reason_code"] == "SYMBOL_RUNTIME_ENABLED"
    assert supported_entries[1]["reason_code"] == "SYMBOL_SUPPORTED_NOT_RUNTIME"


def test_shared_contract_catalog_documents_fact_aliases_and_reason_codes() -> None:
    payload = build_shared_contracts_payload(Settings(postgres_dsn="sqlite+pysqlite:///:memory:"))

    fact_contracts = payload["fact_contracts"]
    research_manifest_summary = fact_contracts["research_manifest_summary"]
    assert research_manifest_summary["delivery_phase"] == "phase_0"
    assert research_manifest_summary["surface_aliases"]["runId"] == "run_id"
    assert "run_id" in research_manifest_summary["machine_fields"]

    balance_summary = fact_contracts["balance_summary"]
    assert balance_summary["status"] == "active"
    assert "GET /v1/balance/summary" in balance_summary["current_surface_paths"]

    control_action_result = fact_contracts["control_action_result"]
    assert "effective_scope" in control_action_result["optional_machine_fields"]
    assert "reason_code" in control_action_result["optional_machine_fields"]

    degraded_mode_status = fact_contracts["degraded_mode_status"]
    assert degraded_mode_status["status"] == "active"
    assert "impact" in degraded_mode_status["human_fields"]
    assert "GET /v1/diagnostics/degraded-mode" in degraded_mode_status["current_surface_paths"]

    diagnostic_replay_summary = fact_contracts["diagnostic_replay_summary"]
    assert "events.reason_code" in diagnostic_replay_summary["machine_fields"]

    control_action_reasons = payload["reason_code_catalog"]["control_actions"]
    assert control_action_reasons == [
        {
            "reason_code": "OPERATOR_REQUEST",
            "meaning": "The action was explicitly requested by an operator.",
        },
        {
            "reason_code": "CANCEL_ALL_FAILED",
            "meaning": "Cancel-all did not complete for every eligible active order.",
        },
    ]

    degraded_mode_reasons = payload["reason_code_catalog"]["degraded_mode"]
    assert any(entry["reason_code"] == "LIVE_DATA_READY" for entry in degraded_mode_reasons)
    assert any(entry["reason_code"] == "MARKET_DATA_MISSING" for entry in degraded_mode_reasons)
