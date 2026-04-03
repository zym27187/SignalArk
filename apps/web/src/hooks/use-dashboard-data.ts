import { startTransition, useEffect, useRef, useState } from "react";

import {
  fetchActiveOrders,
  fetchFillHistory,
  fetchOrderHistory,
  fetchPositions,
  fetchReplayEvents,
  fetchStatus,
  postControlAction,
  type ControlActionKey,
} from "../lib/api";
import { localizeMessage } from "../lib/format";
import type {
  ActiveOrder,
  DashboardActivityFilters,
  DashboardSectionKey,
  FillHistoryEntry,
  HistoryOrder,
  Position,
  ReplayEvent,
  StatusPayload,
} from "../types/api";

const POLL_INTERVAL_MS = 15000;
const DEFAULT_ACTIVITY_FILTERS: DashboardActivityFilters = {
  symbol: "",
  status: "",
  orderId: "",
  traderRunId: "",
  startTime: "",
  endTime: "",
  limit: 12,
};

interface DashboardSnapshot {
  status: StatusPayload | null;
  positions: Position[];
  orders: ActiveOrder[];
  orderHistory: HistoryOrder[];
  fills: FillHistoryEntry[];
  events: ReplayEvent[];
  sectionErrors: Partial<Record<DashboardSectionKey, string>>;
  fetchedAt: string | null;
}

const EMPTY_SNAPSHOT: DashboardSnapshot = {
  status: null,
  positions: [],
  orders: [],
  orderHistory: [],
  fills: [],
  events: [],
  sectionErrors: {},
  fetchedAt: null,
};

function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return localizeMessage(error.message);
  }

  return localizeMessage("Request failed.");
}

function normalizeLimit(value: number): number {
  if (!Number.isFinite(value)) {
    return DEFAULT_ACTIVITY_FILTERS.limit;
  }

  return Math.max(1, Math.min(200, Math.trunc(value)));
}

function toIsoDateTime(value: string): string | undefined {
  const normalized = value.trim();
  if (!normalized) {
    return undefined;
  }

  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) {
    return undefined;
  }

  return parsed.toISOString();
}

function buildSharedActivityQuery(filters: DashboardActivityFilters) {
  const symbol = filters.symbol.trim().toUpperCase();
  const traderRunId = filters.traderRunId.trim();
  return {
    symbol: symbol || undefined,
    traderRunId: traderRunId || undefined,
    startTime: toIsoDateTime(filters.startTime),
    endTime: toIsoDateTime(filters.endTime),
    limit: normalizeLimit(filters.limit),
  };
}

function buildOrderHistoryQuery(filters: DashboardActivityFilters) {
  const sharedQuery = buildSharedActivityQuery(filters);
  const status = filters.status.trim().toUpperCase();
  return {
    ...sharedQuery,
    status: status || undefined,
  };
}

function buildFillHistoryQuery(filters: DashboardActivityFilters) {
  const sharedQuery = buildSharedActivityQuery(filters);
  const orderId = filters.orderId.trim();
  return {
    ...sharedQuery,
    orderId: orderId || undefined,
  };
}

export function useDashboardData() {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot>(EMPTY_SNAPSHOT);
  const [activityFilters, setActivityFilters] =
    useState<DashboardActivityFilters>(DEFAULT_ACTIVITY_FILTERS);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [pendingAction, setPendingAction] = useState<ControlActionKey | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const hasLoadedRef = useRef(false);
  const mountedRef = useRef(false);
  const activityFiltersRef = useRef(activityFilters);

  useEffect(() => {
    activityFiltersRef.current = activityFilters;
  }, [activityFilters]);

  async function refresh(nextFilters?: DashboardActivityFilters) {
    const activeFilters = nextFilters ?? activityFiltersRef.current;
    const sharedActivityQuery = buildSharedActivityQuery(activeFilters);
    const orderHistoryQuery = buildOrderHistoryQuery(activeFilters);
    const fillHistoryQuery = buildFillHistoryQuery(activeFilters);
    const isInitialLoad = !hasLoadedRef.current;

    if (isInitialLoad) {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    const [
      statusResult,
      positionsResult,
      ordersResult,
      orderHistoryResult,
      fillHistoryResult,
      eventsResult,
    ] =
      await Promise.allSettled([
        fetchStatus(),
        fetchPositions(),
        fetchActiveOrders(),
        fetchOrderHistory(orderHistoryQuery),
        fetchFillHistory(fillHistoryQuery),
        fetchReplayEvents(sharedActivityQuery),
      ]);

    if (!mountedRef.current) {
      return;
    }

    hasLoadedRef.current = true;

    startTransition(() => {
      setSnapshot((previous) => ({
        status:
          statusResult.status === "fulfilled" ? statusResult.value : previous.status,
        positions:
          positionsResult.status === "fulfilled"
            ? positionsResult.value.positions
            : previous.positions,
        orders:
          ordersResult.status === "fulfilled" ? ordersResult.value.orders : previous.orders,
        orderHistory:
          orderHistoryResult.status === "fulfilled"
            ? orderHistoryResult.value.orders
            : previous.orderHistory,
        fills:
          fillHistoryResult.status === "fulfilled" ? fillHistoryResult.value.fills : previous.fills,
        events:
          eventsResult.status === "fulfilled" ? eventsResult.value.events : previous.events,
        sectionErrors: {
          status:
            statusResult.status === "rejected"
              ? toErrorMessage(statusResult.reason)
              : undefined,
          positions:
            positionsResult.status === "rejected"
              ? toErrorMessage(positionsResult.reason)
              : undefined,
          orders:
            ordersResult.status === "rejected"
              ? toErrorMessage(ordersResult.reason)
              : undefined,
          orderHistory:
            orderHistoryResult.status === "rejected"
              ? toErrorMessage(orderHistoryResult.reason)
              : undefined,
          fillHistory:
            fillHistoryResult.status === "rejected"
              ? toErrorMessage(fillHistoryResult.reason)
              : undefined,
          events:
            eventsResult.status === "rejected"
              ? toErrorMessage(eventsResult.reason)
              : undefined,
        },
        fetchedAt: new Date().toISOString(),
      }));
    });

    setIsLoading(false);
    setIsRefreshing(false);
  }

  async function performAction(actionKey: ControlActionKey) {
    setPendingAction(actionKey);
    setActionMessage(null);

    try {
      const response = await postControlAction(actionKey);
      if (!mountedRef.current) {
        return;
      }

      setActionMessage(localizeMessage(response.message));
      await refresh();
    } catch (error) {
      if (!mountedRef.current) {
        return;
      }

      setActionMessage(toErrorMessage(error));
    } finally {
      if (mountedRef.current) {
        setPendingAction(null);
      }
    }
  }

  async function applyActivityFilters(nextFilters: DashboardActivityFilters) {
    const normalizedFilters = {
      ...nextFilters,
      symbol: nextFilters.symbol.trim().toUpperCase(),
      status: nextFilters.status.trim().toUpperCase(),
      orderId: nextFilters.orderId.trim(),
      traderRunId: nextFilters.traderRunId.trim(),
      limit: normalizeLimit(nextFilters.limit),
    };
    activityFiltersRef.current = normalizedFilters;
    setActivityFilters(normalizedFilters);
    await refresh(normalizedFilters);
  }

  async function resetActivityFilters() {
    activityFiltersRef.current = DEFAULT_ACTIVITY_FILTERS;
    setActivityFilters(DEFAULT_ACTIVITY_FILTERS);
    await refresh(DEFAULT_ACTIVITY_FILTERS);
  }

  useEffect(() => {
    mountedRef.current = true;
    void refresh();

    const timer = window.setInterval(() => {
      void refresh();
    }, POLL_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      window.clearInterval(timer);
    };
  }, []);

  return {
    snapshot,
    isLoading,
    isRefreshing,
    pendingAction,
    actionMessage,
    activityFilters,
    refresh,
    applyActivityFilters,
    resetActivityFilters,
    performAction,
  };
}

export type DashboardDataState = ReturnType<typeof useDashboardData>;
