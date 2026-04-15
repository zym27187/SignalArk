import type {
  ActiveOrdersPayload,
  BalanceSummaryPayload,
  ControlActionResponse,
  DegradedModeStatusPayload,
  EquityCurvePayload,
  FillHistoryPayload,
  MarketBarsPayload,
  OrderHistoryPayload,
  PositionsPayload,
  ReplayEventsPayload,
  RuntimeBarsPayload,
  RuntimeSymbolRequestResponse,
  SharedContractsPayload,
  SymbolInspectionPayload,
  StatusPayload,
} from "../types/api";
import type {
  ResearchAiSettings,
  ResearchAiSettingsUpdateRequest,
  ResearchAiSnapshotRequest,
  ResearchMode,
  ResearchSnapshot,
} from "../types/research";
export {
  RULE_RESEARCH_REQUIRED_TIMEFRAME as DEFAULT_RULE_RESEARCH_TIMEFRAME,
  RULE_RESEARCH_TEMPLATE_MOVING_AVERAGE_BAND_V1 as DEFAULT_RULE_RESEARCH_TEMPLATE,
} from "../types/research";
import { localizeMessage } from "./format";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
export const DEFAULT_RESEARCH_PREVIEW_LIMIT = 96;
export const DEFAULT_RESEARCH_EVALUATION_LIMIT = 240;
export const DEFAULT_AI_RESEARCH_PREVIEW_LIMIT = 24;
export const DEFAULT_AI_RESEARCH_LOOKBACK_BARS = 12;
export const AI_RESEARCH_REQUEST_TIMEOUT_MS = 30_000;
export const AI_RESEARCH_REQUEST_TIMEOUT_PER_DECISION_MS = 15_000;
export const RULE_RESEARCH_HISTORY_YEAR_OPTIONS = [1, 3, 5] as const;
export type RuleResearchHistoryYears =
  (typeof RULE_RESEARCH_HISTORY_YEAR_OPTIONS)[number];
export const DEFAULT_RULE_RESEARCH_HISTORY_YEARS: RuleResearchHistoryYears = 3;

const RULE_RESEARCH_HISTORY_LIMIT_BY_YEARS: Record<
  RuleResearchHistoryYears,
  number
> = {
  1: 250,
  3: 750,
  5: 1250,
};

type RuntimeConfig = {
  apiBaseUrl?: string;
};

function readRuntimeConfig(): RuntimeConfig | undefined {
  if (typeof window === "undefined") {
    return undefined;
  }
  return window.__SIGNALARK_RUNTIME_CONFIG__;
}

export function resolveApiBaseUrl(runtimeConfig?: RuntimeConfig): string {
  return (
    runtimeConfig?.apiBaseUrl ??
    readRuntimeConfig()?.apiBaseUrl ??
    import.meta.env.VITE_SIGNALARK_API_BASE_URL ??
    DEFAULT_API_BASE_URL
  ).replace(/\/+$/, "");
}

export const API_BASE_URL = resolveApiBaseUrl();

export function resolveRuleResearchLookbackLimit(
  years: RuleResearchHistoryYears,
): number {
  return RULE_RESEARCH_HISTORY_LIMIT_BY_YEARS[years];
}

export const controlActionPaths = {
  pauseStrategy: "/v1/controls/strategy/pause",
  resumeStrategy: "/v1/controls/strategy/resume",
  enableKillSwitch: "/v1/controls/kill-switch/enable",
  disableKillSwitch: "/v1/controls/kill-switch/disable",
  cancelAll: "/v1/controls/cancel-all",
} as const;

export type ControlActionKey = keyof typeof controlActionPaths;

export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

export function resolveAiResearchRequestTimeoutMs(limit?: number): number {
  const resolvedLimit = Math.max(
    1,
    Math.trunc(limit ?? DEFAULT_AI_RESEARCH_PREVIEW_LIMIT),
  );
  const decisionCount = Math.max(
    1,
    resolvedLimit - DEFAULT_AI_RESEARCH_LOOKBACK_BARS + 1,
  );
  return Math.max(
    AI_RESEARCH_REQUEST_TIMEOUT_MS,
    10_000 + decisionCount * AI_RESEARCH_REQUEST_TIMEOUT_PER_DECISION_MS,
  );
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {};
  if (init?.headers instanceof Headers) {
    init.headers.forEach((value, key) => {
      headers[key] = value;
    });
  } else if (Array.isArray(init?.headers)) {
    for (const [key, value] of init.headers) {
      headers[key] = value;
    }
  } else if (init?.headers) {
    Object.assign(headers, init.headers);
  }
  if (!("Accept" in headers) && !("accept" in headers)) {
    headers.Accept = "application/json";
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  });

  const raw = await response.text();
  let payload: unknown = null;

  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = raw;
    }
  }

  if (!response.ok) {
    throw new ApiError(resolveErrorMessage(payload, response.status), response.status, payload);
  }

  return payload as T;
}

function resolveErrorMessage(payload: unknown, status: number): string {
  if (typeof payload === "string" && payload.trim()) {
    return localizeMessage(payload);
  }

  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) {
      return localizeMessage(detail);
    }
  }

  return localizeMessage(`Request failed with status ${status}.`);
}

export async function fetchStatus(): Promise<StatusPayload> {
  return requestJson<StatusPayload>("/v1/status");
}

export async function fetchBalanceSummary(): Promise<BalanceSummaryPayload> {
  return requestJson<BalanceSummaryPayload>("/v1/balance/summary");
}

export async function fetchDegradedMode(): Promise<DegradedModeStatusPayload> {
  return requestJson<DegradedModeStatusPayload>("/v1/diagnostics/degraded-mode");
}

export async function fetchSharedContracts(): Promise<SharedContractsPayload> {
  return requestJson<SharedContractsPayload>("/v1/contracts/shared");
}

export async function fetchPositions(): Promise<PositionsPayload> {
  return requestJson<PositionsPayload>("/v1/positions");
}

export async function inspectSymbol(symbol: string): Promise<SymbolInspectionPayload> {
  const query = new URLSearchParams();
  query.set("symbol", symbol);
  return requestJson<SymbolInspectionPayload>(`/v1/symbols/inspect?${query.toString()}`);
}

export async function submitRuntimeSymbolRequest(params: {
  symbol: string;
  confirm: boolean;
}): Promise<RuntimeSymbolRequestResponse> {
  return requestJson<RuntimeSymbolRequestResponse>("/v1/symbols/runtime-requests", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      symbol: params.symbol,
      confirm: params.confirm,
    }),
  });
}

export async function fetchActiveOrders(): Promise<ActiveOrdersPayload> {
  return requestJson<ActiveOrdersPayload>("/v1/orders/active");
}

interface ActivityQueryParams {
  accountId?: string;
  symbol?: string;
  traderRunId?: string;
  startTime?: string;
  endTime?: string;
  limit?: number;
}

function appendOptionalQuery(query: URLSearchParams, key: string, value: string | undefined) {
  if (value && value.trim()) {
    query.set(key, value);
  }
}

function buildActivityQuery(
  params?: ActivityQueryParams & {
    status?: string;
    orderId?: string;
  },
): string {
  const query = new URLSearchParams();
  appendOptionalQuery(query, "account_id", params?.accountId);
  appendOptionalQuery(query, "symbol", params?.symbol);
  appendOptionalQuery(query, "trader_run_id", params?.traderRunId);
  appendOptionalQuery(query, "start_time", params?.startTime);
  appendOptionalQuery(query, "end_time", params?.endTime);
  appendOptionalQuery(query, "status", params?.status);
  appendOptionalQuery(query, "order_id", params?.orderId);
  query.set("limit", String(params?.limit ?? 12));
  return query.toString();
}

export async function fetchOrderHistory(
  params?: ActivityQueryParams & {
    status?: string;
  },
): Promise<OrderHistoryPayload> {
  return requestJson<OrderHistoryPayload>(`/v1/orders/history?${buildActivityQuery(params)}`);
}

export async function fetchFillHistory(
  params?: ActivityQueryParams & {
    orderId?: string;
  },
): Promise<FillHistoryPayload> {
  return requestJson<FillHistoryPayload>(`/v1/fills/history?${buildActivityQuery(params)}`);
}

export async function fetchMarketBars(params?: {
  symbol?: string;
  timeframe?: string;
  limit?: number;
}): Promise<MarketBarsPayload> {
  const query = new URLSearchParams();
  if (params?.symbol) {
    query.set("symbol", params.symbol);
  }
  if (params?.timeframe) {
    query.set("timeframe", params.timeframe);
  }
  query.set("limit", String(params?.limit ?? 96));
  return requestJson<MarketBarsPayload>(`/v1/market/bars?${query.toString()}`);
}

export async function fetchRuntimeBars(params?: {
  symbol?: string;
  timeframe?: string;
}): Promise<RuntimeBarsPayload> {
  const query = new URLSearchParams();
  if (params?.symbol) {
    query.set("symbol", params.symbol);
  }
  if (params?.timeframe) {
    query.set("timeframe", params.timeframe);
  }
  return requestJson<RuntimeBarsPayload>(`/v1/market/runtime-bars?${query.toString()}`);
}

export async function fetchEquityCurve(params?: {
  symbol?: string;
  timeframe?: string;
  limit?: number;
}): Promise<EquityCurvePayload> {
  const query = new URLSearchParams();
  if (params?.symbol) {
    query.set("symbol", params.symbol);
  }
  if (params?.timeframe) {
    query.set("timeframe", params.timeframe);
  }
  query.set("limit", String(params?.limit ?? 96));
  return requestJson<EquityCurvePayload>(`/v1/portfolio/equity-curve?${query.toString()}`);
}

export async function fetchReplayEvents(
  params?: ActivityQueryParams,
): Promise<ReplayEventsPayload> {
  return requestJson<ReplayEventsPayload>(
    `/v1/diagnostics/replay-events?${buildActivityQuery(params)}`,
  );
}

export async function fetchResearchSnapshot(params?: {
  symbol?: string;
  timeframe?: string;
  limit?: number;
  mode?: ResearchMode;
  slippageModel?: "bar_close_bps" | "directional_close_tiered_bps";
}): Promise<ResearchSnapshot> {
  // This GET endpoint stays reserved for the existing baseline/AI research flow.
  // Configurable rule backtests use POST /v1/research/rule-snapshot so the
  // request body can explicitly pin daily-MA semantics to 1d bars.
  const query = new URLSearchParams();
  if (params?.symbol) {
    query.set("symbol", params.symbol);
  }
  if (params?.timeframe) {
    query.set("timeframe", params.timeframe);
  }
  query.set("limit", String(params?.limit ?? 96));
  if (params?.mode) {
    query.set("mode", params.mode);
  }
  if (params?.slippageModel) {
    query.set("slippage_model", params.slippageModel);
  }
  return requestJson<ResearchSnapshot>(`/v1/research/snapshot?${query.toString()}`);
}

export async function postResearchAiSnapshot(
  params: ResearchAiSnapshotRequest,
): Promise<ResearchSnapshot> {
  const resolvedLimit = params.limit ?? DEFAULT_AI_RESEARCH_PREVIEW_LIMIT;
  const timeoutMs = resolveAiResearchRequestTimeoutMs(resolvedLimit);
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort();
  }, timeoutMs);

  try {
    return await requestJson<ResearchSnapshot>("/v1/research/ai-snapshot", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        symbol: params.symbol,
        timeframe: params.timeframe,
        limit: resolvedLimit,
        provider: params.provider,
        model: params.model,
        baseUrl: params.baseUrl,
        apiKey: params.apiKey,
      }),
      signal: controller.signal,
    });
  } catch (requestError) {
    if (requestError instanceof DOMException && requestError.name === "AbortError") {
      throw new Error("AI research request timed out.");
    }
    throw requestError;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchResearchAiSettings(): Promise<ResearchAiSettings> {
  return requestJson<ResearchAiSettings>("/v1/research/ai-settings");
}

export async function putResearchAiSettings(
  params: ResearchAiSettingsUpdateRequest,
): Promise<ResearchAiSettings> {
  return requestJson<ResearchAiSettings>("/v1/research/ai-settings", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      provider: params.provider,
      model: params.model,
      baseUrl: params.baseUrl,
      apiKey: params.apiKey,
      clearApiKey: params.clearApiKey ?? false,
    }),
  });
}

export async function postControlAction(
  actionKey: ControlActionKey,
): Promise<ControlActionResponse> {
  return requestJson<ControlActionResponse>(controlActionPaths[actionKey], {
    method: "POST",
  });
}
