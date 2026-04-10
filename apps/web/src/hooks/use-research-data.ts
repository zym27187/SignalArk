import { startTransition, useEffect, useRef, useState } from "react";

import {
  DEFAULT_RESEARCH_EVALUATION_LIMIT,
  DEFAULT_RESEARCH_PREVIEW_LIMIT,
  fetchResearchSnapshot,
} from "../lib/api";
import { localizeMessage } from "../lib/format";
import type { ResearchSamplePurpose, ResearchSnapshot } from "../types/research";

interface UseResearchDataOptions {
  enabled: boolean;
  symbol?: string | null;
  timeframe?: string | null;
  samplePurpose: ResearchSamplePurpose;
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return localizeMessage(error.message);
  }

  return localizeMessage("Request failed.");
}

export function useResearchData({
  enabled,
  symbol,
  timeframe,
  samplePurpose,
}: UseResearchDataOptions) {
  const [snapshot, setSnapshot] = useState<ResearchSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(enabled);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const hasLoadedRef = useRef(false);
  const mountedRef = useRef(false);
  const limit =
    samplePurpose === "preview"
      ? DEFAULT_RESEARCH_PREVIEW_LIMIT
      : DEFAULT_RESEARCH_EVALUATION_LIMIT;

  async function refresh() {
    const isInitialLoad = !hasLoadedRef.current;

    if (isInitialLoad) {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }

    try {
      const nextSnapshot = await fetchResearchSnapshot({
        symbol: symbol ?? undefined,
        timeframe: timeframe ?? undefined,
        limit,
        mode: samplePurpose,
      });
      if (!mountedRef.current) {
        return;
      }

      hasLoadedRef.current = true;
      startTransition(() => {
        setSnapshot(nextSnapshot);
        setError(null);
        setFetchedAt(new Date().toISOString());
      });
    } catch (requestError) {
      if (!mountedRef.current) {
        return;
      }

      hasLoadedRef.current = true;
      setError(toErrorMessage(requestError));
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    }
  }

  useEffect(() => {
    mountedRef.current = true;
    hasLoadedRef.current = false;
    setSnapshot(null);
    setError(null);
    setFetchedAt(null);

    if (!enabled) {
      setIsLoading(false);
      setIsRefreshing(false);
      return () => {
        mountedRef.current = false;
      };
    }

    void refresh();
    return () => {
      mountedRef.current = false;
    };
  }, [enabled, symbol, timeframe, samplePurpose]);

  return {
    snapshot,
    error,
    fetchedAt,
    isLoading,
    isRefreshing,
    refresh,
  };
}

export type ResearchDataState = ReturnType<typeof useResearchData>;
