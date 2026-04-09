import type {
  ActiveOrdersPayload,
  ControlActionResponse,
  EquityCurvePayload,
  FillHistoryPayload,
  MarketBarsPayload,
  OrderHistoryPayload,
  PositionsPayload,
  ReplayEventsPayload,
  RuntimeBarsPayload,
  StatusPayload,
} from "../types/api";
import type {
  ResearchAiSettings,
  ResearchAiSettingsUpdateRequest,
  ResearchAiSnapshotRequest,
  ResearchSnapshot,
} from "../types/research";
import { localizeMessage } from "./format";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export const API_BASE_URL = (
  import.meta.env.VITE_SIGNALARK_API_BASE_URL ?? DEFAULT_API_BASE_URL
).replace(/\/+$/, "");

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

export async function fetchPositions(): Promise<PositionsPayload> {
  return requestJson<PositionsPayload>("/v1/positions");
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
}): Promise<ResearchSnapshot> {
  const query = new URLSearchParams();
  if (params?.symbol) {
    query.set("symbol", params.symbol);
  }
  if (params?.timeframe) {
    query.set("timeframe", params.timeframe);
  }
  query.set("limit", String(params?.limit ?? 96));
  return requestJson<ResearchSnapshot>(`/v1/research/snapshot?${query.toString()}`);
}

export async function postResearchAiSnapshot(
  params: ResearchAiSnapshotRequest,
): Promise<ResearchSnapshot> {
  return requestJson<ResearchSnapshot>("/v1/research/ai-snapshot", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      symbol: params.symbol,
      timeframe: params.timeframe,
      limit: params.limit ?? 96,
      provider: params.provider,
      model: params.model,
      baseUrl: params.baseUrl,
      apiKey: params.apiKey,
    }),
  });
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
