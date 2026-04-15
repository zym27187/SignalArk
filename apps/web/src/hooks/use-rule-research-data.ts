import { startTransition, useState } from "react";

import { postResearchRuleSnapshot } from "../lib/api";
import { localizeMessage } from "../lib/format";
import type { ResearchRuleSnapshotRequest, ResearchSnapshot } from "../types/research";

function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return localizeMessage(error.message);
  }

  return localizeMessage("Request failed.");
}

export function useRuleResearchData() {
  const [snapshot, setSnapshot] = useState<ResearchSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastRequest, setLastRequest] = useState<ResearchRuleSnapshotRequest | null>(null);

  async function run(request: ResearchRuleSnapshotRequest) {
    setIsLoading(true);
    setLastRequest(request);
    try {
      const nextSnapshot = await postResearchRuleSnapshot(request);
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

export type RuleResearchDataState = ReturnType<typeof useRuleResearchData>;
