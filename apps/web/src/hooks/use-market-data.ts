import { startTransition, useEffect, useRef, useState } from "react";

import { fetchEquityCurve, fetchMarketBars, fetchRuntimeBars } from "../lib/api";
import { localizeMessage } from "../lib/format";
import type { CandleBar, CurvePoint } from "../types/research";
import type { RuntimeBarsPayload } from "../types/api";

const POLL_INTERVAL_MS = 15000;

interface MarketSnapshot {
  symbol: string | null;
  timeframe: string | null;
  bars: CandleBar[];
  equityCurve: CurvePoint[];
  runtimeBars: RuntimeBarsPayload;
  sectionErrors: {
    bars?: string;
    equityCurve?: string;
    runtimeBars?: string;
  };
  fetchedAt: string | null;
}

const EMPTY_RUNTIME_BARS: RuntimeBarsPayload = {
  filters: {},
  source: "trader_runtime_status",
  trader_run_id: null,
  instance_id: null,
  lifecycle_status: null,
  health_status: null,
  readiness_status: null,
  updated_at: null,
  count: {
    last_seen: 0,
    last_strategy: 0,
  },
  available_streams: [],
  last_seen_bars: [],
  last_strategy_bars: [],
  degraded_mode: {
    status: "missing",
    reason_code: "RUNTIME_STATUS_MISSING",
    message: "当前还没有活跃 trader runtime 状态。",
    data_source: "missing",
    effective_at: "",
    impact: "市场页当前只能展示空状态或前端补位结果。",
    suggested_action: "先等待 runtime 启动并落下最新状态。",
  },
};

const EMPTY_MARKET_SNAPSHOT: MarketSnapshot = {
  symbol: null,
  timeframe: null,
  bars: [],
  equityCurve: [],
  runtimeBars: EMPTY_RUNTIME_BARS,
  sectionErrors: {},
  fetchedAt: null,
};

function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return localizeMessage(error.message);
  }

  return localizeMessage("Request failed.");
}

interface UseMarketDataOptions {
  enabled: boolean;
  symbol?: string | null;
  timeframe?: string | null;
}

export function useMarketData({ enabled, symbol, timeframe }: UseMarketDataOptions) {
  const [snapshot, setSnapshot] = useState<MarketSnapshot>(EMPTY_MARKET_SNAPSHOT);
  const [isLoading, setIsLoading] = useState(enabled);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const hasLoadedRef = useRef(false);
  const mountedRef = useRef(false);

  async function refresh() {
    const isInitialLoad = !hasLoadedRef.current;

    if (isInitialLoad) {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    const request = {
      symbol: symbol ?? undefined,
      timeframe: timeframe ?? undefined,
      limit: 96,
    };
    const [barsResult, equityCurveResult, runtimeBarsResult] = await Promise.allSettled([
      fetchMarketBars(request),
      fetchEquityCurve(request),
      fetchRuntimeBars({
        symbol: symbol ?? undefined,
        timeframe: timeframe ?? undefined,
      }),
    ]);

    if (!mountedRef.current) {
      return;
    }

    hasLoadedRef.current = true;

    startTransition(() => {
      setSnapshot((previous) => ({
        symbol:
          barsResult.status === "fulfilled"
            ? barsResult.value.symbol
            : equityCurveResult.status === "fulfilled"
              ? equityCurveResult.value.symbol
              : previous.symbol,
        timeframe:
          barsResult.status === "fulfilled"
            ? barsResult.value.timeframe
            : equityCurveResult.status === "fulfilled"
              ? equityCurveResult.value.timeframe
              : previous.timeframe,
        bars: barsResult.status === "fulfilled" ? barsResult.value.bars : previous.bars,
        equityCurve:
          equityCurveResult.status === "fulfilled"
            ? equityCurveResult.value.points
            : previous.equityCurve,
        runtimeBars:
          runtimeBarsResult.status === "fulfilled"
            ? runtimeBarsResult.value
            : previous.runtimeBars,
        sectionErrors: {
          bars: barsResult.status === "rejected" ? toErrorMessage(barsResult.reason) : undefined,
          equityCurve:
            equityCurveResult.status === "rejected"
              ? toErrorMessage(equityCurveResult.reason)
              : undefined,
          runtimeBars:
            runtimeBarsResult.status === "rejected"
              ? toErrorMessage(runtimeBarsResult.reason)
              : undefined,
        },
        fetchedAt: new Date().toISOString(),
      }));
    });

    setIsLoading(false);
    setIsRefreshing(false);
  }

  useEffect(() => {
    mountedRef.current = true;
    hasLoadedRef.current = false;
    setSnapshot({
      ...EMPTY_MARKET_SNAPSHOT,
      symbol: symbol ?? null,
      timeframe: timeframe ?? null,
    });

    if (!enabled) {
      setIsLoading(false);
      setIsRefreshing(false);
      return () => {
        mountedRef.current = false;
      };
    }

    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, POLL_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      window.clearInterval(timer);
    };
  }, [enabled, symbol, timeframe]);

  return {
    snapshot,
    isLoading,
    isRefreshing,
    refresh,
  };
}

export type MarketDataState = ReturnType<typeof useMarketData>;
