import { startTransition, useEffect, useRef, useState } from "react";

import { fetchResearchAiSettings, putResearchAiSettings } from "../lib/api";
import { localizeMessage } from "../lib/format";
import type {
  ResearchAiSettings,
  ResearchAiSettingsUpdateRequest,
} from "../types/research";

function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return localizeMessage(error.message);
  }

  return localizeMessage("Request failed.");
}

export function useAiResearchSettings({ enabled }: { enabled: boolean }) {
  const [settings, setSettings] = useState<ResearchAiSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(enabled);
  const [isSaving, setIsSaving] = useState(false);

  const mountedRef = useRef(false);

  async function refresh() {
    setIsLoading(true);
    try {
      const nextSettings = await fetchResearchAiSettings();
      if (!mountedRef.current) {
        return null;
      }
      startTransition(() => {
        setSettings(nextSettings);
        setError(null);
      });
      return nextSettings;
    } catch (requestError) {
      if (!mountedRef.current) {
        return null;
      }
      setError(toErrorMessage(requestError));
      return null;
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }

  async function save(request: ResearchAiSettingsUpdateRequest) {
    setIsSaving(true);
    try {
      const nextSettings = await putResearchAiSettings(request);
      if (!mountedRef.current) {
        return null;
      }
      startTransition(() => {
        setSettings(nextSettings);
        setError(null);
      });
      return nextSettings;
    } catch (requestError) {
      if (!mountedRef.current) {
        return null;
      }
      setError(toErrorMessage(requestError));
      return null;
    } finally {
      if (mountedRef.current) {
        setIsSaving(false);
      }
    }
  }

  useEffect(() => {
    mountedRef.current = true;
    if (!enabled) {
      setIsLoading(false);
      return () => {
        mountedRef.current = false;
      };
    }

    void refresh();
    return () => {
      mountedRef.current = false;
    };
  }, [enabled]);

  return {
    settings,
    error,
    isLoading,
    isSaving,
    refresh,
    save,
  };
}

export type AiResearchSettingsState = ReturnType<typeof useAiResearchSettings>;
