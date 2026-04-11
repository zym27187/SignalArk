import type { CandleBar, CurvePoint } from "./research";

export type SymbolNameMap = Record<string, string>;

export interface SharedContractPlane {
  key: string;
  label: string;
  responsibility: string;
  owns: string[];
  does_not_own: string[];
}

export interface SharedContractLayerDefinition {
  key: string;
  label: string;
  definition: string;
  activates_trading: boolean;
}

export interface SharedContractSymbolLayerEntry {
  symbol: string;
  display_name: string | null;
  layers: {
    observed: boolean;
    supported: boolean;
    runtime_enabled: boolean;
  };
  reason_code: string;
  message: string;
}

export interface SharedContractSymbolLayerContract {
  layer_order: string[];
  layers: SharedContractLayerDefinition[];
  transition_rules: string[];
  current_boundaries: {
    supported_symbols: string[];
    runtime_symbols: string[];
    runtime_subset_of_supported: boolean;
  };
  current_supported_entries: SharedContractSymbolLayerEntry[];
  examples: SharedContractSymbolLayerEntry[];
}

export interface SharedContractFactDefinition {
  status: string;
  delivery_phase: string;
  owner_plane: string;
  machine_fields: string[];
  human_fields?: string[];
  optional_machine_fields?: string[];
  detail_collections?: string[];
  current_surface_paths?: string[];
  surface_aliases?: Record<string, string>;
  notes: string[];
}

export interface SharedContractReasonCode {
  reason_code: string;
  meaning: string;
}

export interface NamingDifferenceAuditEntry {
  surface: string;
  current_meaning: string;
  decision: string;
  follow_up_phase: string;
}

export interface SharedContractsPayload {
  contract_version: string;
  phase: string;
  generated_from: {
    endpoint: string;
    config_entrypoint: string;
  };
  planes: SharedContractPlane[];
  naming_conventions: {
    operational_api_payloads: string;
    research_snapshot_payload: string;
    mcp_tool_names: string;
    canonical_fact_ids: string[];
    compatibility_rule: string;
  };
  symbol_layer_contract: SharedContractSymbolLayerContract;
  fact_contracts: Record<string, SharedContractFactDefinition>;
  reason_code_catalog: Record<string, SharedContractReasonCode[]>;
  naming_differences_audit: NamingDifferenceAuditEntry[];
}

export interface StatusPayload {
  trader_run_id: string | null;
  instance_id: string | null;
  account_id: string;
  control_state: string;
  strategy_enabled: boolean;
  kill_switch_active: boolean;
  protection_mode_active: boolean;
  ready: boolean;
  status: string;
  health_status: string;
  lifecycle_status: string;
  market_data_fresh: boolean;
  market_state_available: boolean;
  latest_final_bar_time: string | null;
  current_trading_phase: string | null;
  lease_owner_instance_id: string | null;
  lease_expires_at: string | null;
  last_heartbeat_at: string | null;
  fencing_token: number | null;
  last_cancel_all_at?: string | null;
  cancel_all_token?: number;
  message?: string | null;
  as_of?: string;
  service?: string;
  env?: string;
  execution_mode?: string;
  exchange?: string;
  symbols?: string[];
  symbol_names?: SymbolNameMap;
}

export interface Position {
  account_id: string;
  exchange: string;
  symbol: string;
  qty: string;
  sellable_qty: string;
  avg_entry_price: string;
  mark_price: string;
  unrealized_pnl: string;
  realized_pnl: string;
  status: string;
  updated_at: string;
}

export interface PositionsPayload {
  account_id: string;
  positions: Position[];
}

export interface SymbolInspectionPayload {
  raw_input: string;
  normalized_symbol: string;
  format_valid: boolean;
  market: string;
  market_label: string;
  venue: string | null;
  venue_label: string;
  display_name: string | null;
  name_status: "available" | "missing";
  layers: {
    observed: boolean;
    supported: boolean;
    runtime_enabled: boolean;
  };
  reason_code: string;
  message: string;
  runtime_activation: {
    requires_confirmation: boolean;
    phase: string;
    can_apply_now: boolean;
    message: string;
  };
}

export interface ActiveOrder {
  order_id: string;
  order_intent_id: string;
  symbol: string;
  side: string;
  order_type: string;
  qty: string;
  filled_qty: string;
  status: string;
  reduce_only: boolean;
  submitted_at: string;
  updated_at: string;
}

export interface ActiveOrdersPayload {
  account_id: string;
  orders: ActiveOrder[];
}

export interface HistoryOrder {
  order_id: string;
  order_intent_id: string;
  signal_id: string;
  trader_run_id: string;
  account_id: string;
  exchange_order_id: string | null;
  symbol: string;
  side: string;
  order_type: string;
  time_in_force: string;
  qty: string;
  price: string | null;
  filled_qty: string;
  avg_fill_price: string | null;
  status: string;
  reduce_only: boolean;
  risk_decision: string;
  risk_reason: string | null;
  submitted_at: string;
  updated_at: string;
  last_error_code: string | null;
  last_error_message: string | null;
}

export interface OrderHistoryPayload {
  filters: Record<string, unknown>;
  count: number;
  orders: HistoryOrder[];
}

export interface FillHistoryEntry {
  fill_id: string;
  order_id: string;
  order_intent_id: string;
  trader_run_id: string;
  account_id: string;
  exchange_fill_id: string | null;
  symbol: string;
  side: string;
  qty: string;
  price: string;
  fee: string;
  fee_asset: string | null;
  liquidity_type: string;
  fill_time: string;
  created_at: string;
  reduce_only: boolean;
}

export interface FillHistoryPayload {
  filters: Record<string, unknown>;
  count: number;
  fills: FillHistoryEntry[];
}

export interface ReplayEvent {
  event_id: string;
  event_type: string;
  source: string;
  trader_run_id: string | null;
  account_id: string | null;
  exchange: string | null;
  symbol: string | null;
  related_object_type: string | null;
  event_time: string;
  ingest_time: string;
  created_at: string;
  payload_json: Record<string, unknown> | null;
}

export interface ReplayEventsPayload {
  filters: Record<string, unknown>;
  count: number;
  events: ReplayEvent[];
}

export interface MarketBarsPayload {
  symbol: string;
  timeframe: string;
  count: number;
  source: string;
  bars: CandleBar[];
}

export interface RuntimeBarSnapshot {
  stream_key: string;
  bar_key: string;
  exchange: string;
  symbol: string;
  timeframe: string;
  bar_start_time: string;
  bar_end_time: string;
  event_time: string;
  ingest_time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  quote_volume: number | null;
  trade_count: number | null;
  closed: boolean;
  final: boolean;
  source_kind: string | null;
  trade_date: string | null;
  trading_phase: string | null;
}

export interface RuntimeBarStreamSummary {
  stream_key: string;
  symbol: string | null;
  timeframe: string | null;
  exchange: string | null;
  last_seen_event_time: string | null;
  last_strategy_event_time: string | null;
}

export interface RuntimeBarsPayload {
  filters: Record<string, unknown>;
  source: string;
  trader_run_id: string | null;
  instance_id: string | null;
  lifecycle_status: string | null;
  health_status: string | null;
  readiness_status: string | null;
  updated_at: string | null;
  count: {
    last_seen: number;
    last_strategy: number;
  };
  available_streams: RuntimeBarStreamSummary[];
  last_seen_bars: RuntimeBarSnapshot[];
  last_strategy_bars: RuntimeBarSnapshot[];
}

export interface EquityCurvePayload {
  account_id: string;
  symbol: string;
  timeframe: string;
  count: number;
  source: string;
  scope?: string;
  anchor_symbol?: string;
  valuation_symbols?: string[];
  points: CurvePoint[];
}

export interface ControlActionResponse {
  accepted: boolean;
  control_state: string;
  trader_run_id: string | null;
  instance_id: string | null;
  effective_at: string;
  message: string;
  requested_order_count?: number;
  cancelled_order_count?: number;
  skipped_order_count?: number;
}

export interface DashboardControlActionResult {
  actionKey: string;
  actionLabel: string;
  accepted: boolean;
  controlState: string | null;
  requestedAt: string;
  effectiveAt: string | null;
  message: string;
  requestedOrderCount: number | null;
  cancelledOrderCount: number | null;
  skippedOrderCount: number | null;
}

export interface DashboardActivityFilters {
  symbol: string;
  status: string;
  orderId: string;
  traderRunId: string;
  startTime: string;
  endTime: string;
  limit: number;
}

export type DashboardSectionKey =
  | "status"
  | "positions"
  | "orders"
  | "orderHistory"
  | "fillHistory"
  | "events";
