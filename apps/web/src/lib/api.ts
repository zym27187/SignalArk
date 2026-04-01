import type {
  ActiveOrdersPayload,
  ControlActionResponse,
  PositionsPayload,
  ReplayEventsPayload,
  StatusPayload,
} from "../types/api";

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
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
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
    return payload;
  }

  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
  }

  return `Request failed with status ${status}.`;
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

export async function fetchReplayEvents(limit = 12): Promise<ReplayEventsPayload> {
  return requestJson<ReplayEventsPayload>(`/v1/diagnostics/replay-events?limit=${limit}`);
}

export async function postControlAction(
  actionKey: ControlActionKey,
): Promise<ControlActionResponse> {
  return requestJson<ControlActionResponse>(controlActionPaths[actionKey], {
    method: "POST",
  });
}

