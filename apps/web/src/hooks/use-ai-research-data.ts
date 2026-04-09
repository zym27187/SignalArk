import { startTransition, useState } from "react";

import { postResearchAiSnapshot } from "../lib/api";
import { localizeMessage } from "../lib/format";
import type { ResearchAiSnapshotRequest, ResearchSnapshot } from "../types/research";

function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return localizeMessage(error.message);
  }

  return localizeMessage("Request failed.");
}

export function useAiResearchData() {
  const [snapshot, setSnapshot] = useState<ResearchSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastRequest, setLastRequest] = useState<ResearchAiSnapshotRequest | null>(null);

  async function run(request: ResearchAiSnapshotRequest) {
    setIsLoading(true);
    setLastRequest(request);
    try {
      const nextSnapshot = await postResearchAiSnapshot(request);
      startTransition(() => {
        setSnapshot(nextSnapshot);
        setError(null);
        setFetchedAt(new Date().toISOString());
      });
      return nextSnapshot;
    } catch (requestError) {
      setError(toErrorMessage(requestError));
      return null;
    } finally {
      setIsLoading(false);
    }
  }

  async function refresh() {
    if (lastRequest === null) {
      return null;
    }
    return run(lastRequest);
  }

  function reset() {
    setSnapshot(null);
    setError(null);
    setFetchedAt(null);
    setLastRequest(null);
    setIsLoading(false);
  }

  return {
    snapshot,
    error,
    fetchedAt,
    isLoading,
    isRefreshing: isLoading,
    lastRequest,
    run,
    refresh,
    reset,
  };
}

export type AiResearchDataState = ReturnType<typeof useAiResearchData>;
