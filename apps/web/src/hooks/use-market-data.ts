import { startTransition, useEffect, useRef, useState } from "react";

import { fetchEquityCurve, fetchMarketBars } from "../lib/api";
import { localizeMessage } from "../lib/format";
import type { CandleBar, CurvePoint } from "../types/research";

const POLL_INTERVAL_MS = 15000;

interface MarketSnapshot {
  symbol: string | null;
  timeframe: string | null;
  bars: CandleBar[];
  equityCurve: CurvePoint[];
  sectionErrors: {
    bars?: string;
    equityCurve?: string;
  };
  fetchedAt: string | null;
}

const EMPTY_MARKET_SNAPSHOT: MarketSnapshot = {
  symbol: null,
  timeframe: null,
  bars: [],
  equityCurve: [],
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
    const [barsResult, equityCurveResult] = await Promise.allSettled([
      fetchMarketBars(request),
      fetchEquityCurve(request),
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
        sectionErrors: {
          bars: barsResult.status === "rejected" ? toErrorMessage(barsResult.reason) : undefined,
          equityCurve:
            equityCurveResult.status === "rejected"
              ? toErrorMessage(equityCurveResult.reason)
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
