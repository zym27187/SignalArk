import type { CandleBar, CurvePoint } from "./research";

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

export interface EquityCurvePayload {
  account_id: string;
  symbol: string;
  timeframe: string;
  count: number;
  source: string;
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

export type DashboardSectionKey = "status" | "positions" | "orders" | "events";
