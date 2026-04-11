"""V2 Phase 0 shared contract catalog for cross-plane semantics."""

from __future__ import annotations

from typing import Any

from .settings import Settings

V2_SHARED_CONTRACT_VERSION = "v2.phase0.2026-04-11"
PHASE_0_SHARED_CONTRACT_ENDPOINT = "/v1/contracts/shared"

CONTROL_ACTION_REASON_OPERATOR_REQUEST = "OPERATOR_REQUEST"
CONTROL_ACTION_REASON_CANCEL_ALL_FAILED = "CANCEL_ALL_FAILED"


def build_shared_contracts_payload(settings: Settings) -> dict[str, object]:
    """Build the canonical Phase 0 contract catalog for API, MCP, and frontend consumers."""
    return {
        "contract_version": V2_SHARED_CONTRACT_VERSION,
        "phase": "phase_0",
        "generated_from": {
            "endpoint": PHASE_0_SHARED_CONTRACT_ENDPOINT,
            "config_entrypoint": settings.shared_config_entrypoint,
        },
        "planes": _build_plane_contracts(),
        "naming_conventions": _build_naming_conventions(),
        "symbol_layer_contract": _build_symbol_layer_contract(settings),
        "fact_contracts": _build_fact_contracts(),
        "reason_code_catalog": _build_reason_code_catalog(),
        "naming_differences_audit": _build_naming_differences_audit(),
    }


def _build_plane_contracts() -> list[dict[str, object]]:
    return [
        {
            "key": "research_plane",
            "label": "Research Plane",
            "responsibility": (
                "Produce reproducible snapshots, manifests, and comparisons without mutating "
                "the active trader runtime."
            ),
            "owns": [
                "research_snapshot",
                "research_manifest_summary",
                "sample_metadata",
                "segment_analysis",
            ],
            "does_not_own": [
                "runtime_control_state",
                "live_order_submission",
                "operator_control_actions",
            ],
        },
        {
            "key": "trading_plane",
            "label": "Trading Plane",
            "responsibility": (
                "Own closed_bar-driven signal evaluation, risk checks, OMS, execution facts, "
                "and runtime state transitions."
            ),
            "owns": [
                "closed_bar_trigger",
                "signal_to_order_intent_pipeline",
                "execution_facts",
                "runtime_bar_audit",
            ],
            "does_not_own": [
                "operator_confirmation_ui",
                "research_snapshot_comparison",
                "ad_hoc_manual_diagnostics",
            ],
        },
        {
            "key": "control_plane",
            "label": "Control Plane",
            "responsibility": (
                "Expose read-only status, control actions, and diagnostics on top of the "
                "trading plane without redefining trading semantics."
            ),
            "owns": [
                "status_views",
                "control_action_result",
                "diagnostic_replay",
                "shared_contract_catalog",
            ],
            "does_not_own": [
                "strategy_decision_logic",
                "market_data_ingestion",
                "research_result_generation",
            ],
        },
    ]


def _build_naming_conventions() -> dict[str, object]:
    return {
        "operational_api_payloads": "snake_case",
        "research_snapshot_payload": "camelCase",
        "mcp_tool_names": "verb_phrases_with_snake_case",
        "canonical_fact_ids": [
            "balance_summary",
            "control_action_result",
            "runtime_bar_audit_summary",
            "degraded_mode_status",
            "research_manifest_summary",
        ],
        "compatibility_rule": (
            "Existing V1 payload surfaces stay backward compatible; the shared contract "
            "catalog documents the canonical meaning and aliases that later phases must follow."
        ),
    }


def _build_symbol_layer_contract(settings: Settings) -> dict[str, object]:
    supported_set = set(settings.supported_symbols)
    runtime_set = set(settings.symbols)
    current_entries = [
        {
            "symbol": symbol,
            "display_name": settings.symbol_names.get(symbol),
            "layers": {
                "observed": True,
                "supported": symbol in supported_set,
                "runtime_enabled": symbol in runtime_set,
            },
            "reason_code": (
                "SYMBOL_RUNTIME_ENABLED"
                if symbol in runtime_set
                else "SYMBOL_SUPPORTED_NOT_RUNTIME"
            ),
            "message": (
                "Symbol is currently enabled for trader runtime."
                if symbol in runtime_set
                else "Symbol is supported by the system but not enabled for trader runtime."
            ),
        }
        for symbol in settings.supported_symbols
    ]
    return {
        "layer_order": ["observed", "supported", "runtime_enabled"],
        "layers": [
            {
                "key": "observed",
                "label": "Observed",
                "definition": (
                    "The symbol was entered or tracked for watching, validation, or research "
                    "candidate purposes."
                ),
                "activates_trading": False,
            },
            {
                "key": "supported",
                "label": "Supported",
                "definition": (
                    "The system has naming, exchange-rule, and base validation support for the "
                    "symbol."
                ),
                "activates_trading": False,
            },
            {
                "key": "runtime_enabled",
                "label": "Runtime Enabled",
                "definition": (
                    "The symbol is part of the active trader runtime scope and can affect live "
                    "paper-trading decisions."
                ),
                "activates_trading": True,
            },
        ],
        "transition_rules": [
            "observed does not imply supported symbol metadata or exchange-rule readiness",
            "supported implies observed",
            "runtime_enabled implies supported",
            "adding a symbol in the UI must not auto-enable runtime trading",
            "runtime scope changes require explicit confirmation and impact messaging",
        ],
        "current_boundaries": {
            "supported_symbols": list(settings.supported_symbols),
            "runtime_symbols": list(settings.symbols),
            "runtime_subset_of_supported": runtime_set.issubset(supported_set),
        },
        "current_supported_entries": current_entries,
        "examples": [
            {
                "symbol": "300750.SZ",
                "display_name": None,
                "layers": {
                    "observed": True,
                    "supported": False,
                    "runtime_enabled": False,
                },
                "reason_code": "SYMBOL_OBSERVED_ONLY",
                "message": "Observed only; the symbol is not yet part of supported_symbols.",
            },
            {
                "symbol": settings.supported_symbols[0],
                "display_name": settings.symbol_names.get(settings.supported_symbols[0]),
                "layers": {
                    "observed": True,
                    "supported": True,
                    "runtime_enabled": settings.supported_symbols[0] in runtime_set,
                },
                "reason_code": (
                    "SYMBOL_RUNTIME_ENABLED"
                    if settings.supported_symbols[0] in runtime_set
                    else "SYMBOL_SUPPORTED_NOT_RUNTIME"
                ),
                "message": (
                    "Supported symbol example aligned with the current runtime boundary."
                ),
            },
        ],
    }


def _build_fact_contracts() -> dict[str, dict[str, Any]]:
    return {
        "balance_summary": {
            "status": "planned",
            "delivery_phase": "phase_2",
            "owner_plane": "control_plane",
            "machine_fields": [
                "cash_balance",
                "available_cash",
                "frozen_cash",
                "equity",
                "as_of_time",
            ],
            "human_fields": ["summary_message"],
            "notes": [
                "Phase 0 fixes the field semantics but does not add the full balance endpoint yet.",
                "available_cash and frozen_cash must explain why total cash differs from equity.",
            ],
        },
        "control_action_result": {
            "status": "active",
            "delivery_phase": "phase_0",
            "owner_plane": "control_plane",
            "machine_fields": [
                "accepted",
                "control_state",
                "effective_at",
                "trader_run_id",
                "instance_id",
            ],
            "optional_machine_fields": [
                "effective_scope",
                "reason_code",
                "requested_order_count",
                "cancelled_order_count",
                "skipped_order_count",
            ],
            "human_fields": ["message"],
            "current_surface_paths": [
                "POST /v1/controls/strategy/pause",
                "POST /v1/controls/strategy/resume",
                "POST /v1/controls/kill-switch/enable",
                "POST /v1/controls/kill-switch/disable",
                "POST /v1/controls/cancel-all",
            ],
            "notes": [
                "message is the operator-facing summary.",
                "reason_code is the machine-facing classification when present.",
            ],
        },
        "runtime_bar_audit_summary": {
            "status": "active",
            "delivery_phase": "phase_0",
            "owner_plane": "trading_plane",
            "machine_fields": [
                "source",
                "trader_run_id",
                "instance_id",
                "lifecycle_status",
                "health_status",
                "readiness_status",
                "updated_at",
                "count.last_seen",
                "count.last_strategy",
            ],
            "detail_collections": [
                "available_streams",
                "last_seen_bars",
                "last_strategy_bars",
            ],
            "current_surface_paths": ["GET /v1/market/runtime-bars"],
            "notes": [
                "available_streams summarizes per-stream freshness.",
                "last_seen_bars captures what runtime observed; last_strategy_bars captures what "
                "was actually forwarded into strategy evaluation.",
            ],
        },
        "degraded_mode_status": {
            "status": "planned",
            "delivery_phase": "phase_3",
            "owner_plane": "control_plane",
            "machine_fields": [
                "status",
                "reason_code",
                "data_source",
                "effective_at",
            ],
            "human_fields": ["message"],
            "notes": [
                "Phase 0 fixes the field names and reason code families for later implementation.",
                "degraded mode must distinguish fixture data, missing data, and uncertain state.",
            ],
        },
        "research_manifest_summary": {
            "status": "active",
            "delivery_phase": "phase_0",
            "owner_plane": "research_plane",
            "machine_fields": [
                "run_id",
                "account_id",
                "strategy_id",
                "handler_name",
                "symbols",
                "timeframe",
                "bar_count",
                "start_time",
                "end_time",
                "initial_cash",
                "slippage_bps",
                "fee_model",
                "slippage_model",
                "partial_fill_model",
                "unfilled_qty_handling",
                "execution_constraints",
                "data_fingerprint",
                "manifest_fingerprint",
            ],
            "human_fields": ["description"],
            "current_surface_paths": ["GET /v1/research/snapshot -> manifest"],
            "surface_aliases": {
                "runId": "run_id",
                "accountId": "account_id",
                "strategyId": "strategy_id",
                "handlerName": "handler_name",
                "startTime": "start_time",
                "endTime": "end_time",
                "initialCash": "initial_cash",
                "slippageBps": "slippage_bps",
                "feeModel": "fee_model",
                "slippageModel": "slippage_model",
                "partialFillModel": "partial_fill_model",
                "unfilledQtyHandling": "unfilled_qty_handling",
                "executionConstraints": "execution_constraints",
                "dataFingerprint": "data_fingerprint",
                "manifestFingerprint": "manifest_fingerprint",
            },
            "notes": [
                "Research payload keeps existing camelCase for compatibility.",
                (
                    "The catalog defines the canonical alias set that later comparison "
                    "features must reuse."
                ),
            ],
        },
    }


def _build_reason_code_catalog() -> dict[str, list[dict[str, str]]]:
    return {
        "symbol_layering": [
            {
                "reason_code": "SYMBOL_OBSERVED_ONLY",
                "meaning": (
                    "The symbol is tracked or entered but not yet part of "
                    "supported_symbols."
                ),
            },
            {
                "reason_code": "SYMBOL_SUPPORTED_NOT_RUNTIME",
                "meaning": "The symbol is supported by the system but not enabled for runtime.",
            },
            {
                "reason_code": "SYMBOL_RUNTIME_ENABLED",
                "meaning": "The symbol is currently enabled inside SIGNALARK_SYMBOLS.",
            },
            {
                "reason_code": "INVALID_SYMBOL_FORMAT",
                "meaning": "The symbol does not satisfy the A-share code format contract.",
            },
            {
                "reason_code": "SYMBOL_NAME_MISSING",
                "meaning": "The symbol is normalized but a display name is not available yet.",
            },
        ],
        "control_actions": [
            {
                "reason_code": CONTROL_ACTION_REASON_OPERATOR_REQUEST,
                "meaning": "The action was explicitly requested by an operator.",
            },
            {
                "reason_code": CONTROL_ACTION_REASON_CANCEL_ALL_FAILED,
                "meaning": "Cancel-all did not complete for every eligible active order.",
            },
        ],
        "degraded_mode": [
            {
                "reason_code": "CONTROL_PLANE_SCHEMA_MISSING",
                "meaning": "The control-plane persistence schema is not initialized yet.",
            },
            {
                "reason_code": "MARKET_DATA_STALE",
                "meaning": "Market data is present but too old to trust as fresh runtime input.",
            },
            {
                "reason_code": "LEASE_NOT_HELD",
                "meaning": "The active runtime no longer owns the account lease.",
            },
            {
                "reason_code": "PROTECTION_MODE_ACTIVE",
                "meaning": (
                    "Trading is constrained because reconciliation or runtime health is "
                    "not safe."
                ),
            },
            {
                "reason_code": "FIXTURE_DATA_IN_USE",
                "meaning": "The system is running with fixture data instead of live market data.",
            },
        ],
        "research": [
            {
                "reason_code": "RESEARCH_SAMPLE_TOO_SHORT",
                "meaning": (
                    "The requested bar window is too short for the intended comparison "
                    "mode."
                ),
            },
            {
                "reason_code": "RESEARCH_DATA_UNAVAILABLE",
                "meaning": (
                    "No finalized bars are available to build the requested research "
                    "snapshot."
                ),
            },
        ],
    }


def _build_naming_differences_audit() -> list[dict[str, str]]:
    return [
        {
            "surface": "status_payload.symbols",
            "current_meaning": "active runtime symbols",
            "decision": (
                "Keep `symbols` as the runtime boundary for V1 compatibility and treat "
                "`supported_symbols` as the wider system support boundary."
            ),
            "follow_up_phase": "phase_1",
        },
        {
            "surface": "research_snapshot.manifest.runId and other camelCase fields",
            "current_meaning": "research manifest summary",
            "decision": (
                "Keep the camelCase research payload surface, but document canonical snake_case "
                "aliases in the shared contract catalog."
            ),
            "follow_up_phase": "phase_4",
        },
        {
            "surface": "MCP tool names versus HTTP API paths",
            "current_meaning": "read-only control-plane access",
            "decision": (
                "Tool names may remain verb-oriented, but returned payload semantics must match "
                "the HTTP contract catalog."
            ),
            "follow_up_phase": "phase_3",
        },
    ]
