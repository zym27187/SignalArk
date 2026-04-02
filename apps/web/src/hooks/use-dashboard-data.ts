import { startTransition, useEffect, useRef, useState } from "react";

import {
  fetchActiveOrders,
  fetchPositions,
  fetchReplayEvents,
  fetchStatus,
  postControlAction,
  type ControlActionKey,
} from "../lib/api";
import type {
  ActiveOrder,
  DashboardSectionKey,
  Position,
  ReplayEvent,
  StatusPayload,
} from "../types/api";

const POLL_INTERVAL_MS = 15000;

interface DashboardSnapshot {
  status: StatusPayload | null;
  positions: Position[];
  orders: ActiveOrder[];
  events: ReplayEvent[];
  sectionErrors: Partial<Record<DashboardSectionKey, string>>;
  fetchedAt: string | null;
}

const EMPTY_SNAPSHOT: DashboardSnapshot = {
  status: null,
  positions: [],
  orders: [],
  events: [],
  sectionErrors: {},
  fetchedAt: null,
};

function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return "Request failed.";
}

export function useDashboardData() {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot>(EMPTY_SNAPSHOT);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [pendingAction, setPendingAction] = useState<ControlActionKey | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const hasLoadedRef = useRef(false);
  const mountedRef = useRef(false);

  async function refresh() {
    const isInitialLoad = !hasLoadedRef.current;

    if (isInitialLoad) {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    const [statusResult, positionsResult, ordersResult, eventsResult] =
      await Promise.allSettled([
        fetchStatus(),
        fetchPositions(),
        fetchActiveOrders(),
        fetchReplayEvents(),
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

      setActionMessage(response.message);
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
    refresh,
    performAction,
  };
}

export type DashboardDataState = ReturnType<typeof useDashboardData>;
