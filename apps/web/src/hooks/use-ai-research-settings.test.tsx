import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAiResearchSettings } from "./use-ai-research-settings";
import { fetchResearchAiSettings, putResearchAiSettings } from "../lib/api";

vi.mock("../lib/api", () => ({
  fetchResearchAiSettings: vi.fn(),
  putResearchAiSettings: vi.fn(),
}));

const mockedFetchResearchAiSettings = vi.mocked(fetchResearchAiSettings);
const mockedPutResearchAiSettings = vi.mocked(putResearchAiSettings);

describe("useAiResearchSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  it("loads persisted AI settings when enabled", async () => {
    mockedFetchResearchAiSettings.mockResolvedValueOnce({
      accountId: "paper_account_001",
      provider: "openai_compatible",
      model: "gpt-5.4",
      baseUrl: "https://api.openai.com/v1",
      hasApiKey: true,
      apiKeyHint: "sk-...cret",
      updatedAt: "2026-04-09T18:00:00+08:00",
    });

    const { result } = renderHook(() => useAiResearchSettings({ enabled: true }));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.settings?.hasApiKey).toBe(true);
    expect(result.current.settings?.apiKeyHint).toBe("sk-...cret");
  });

  it("saves persisted AI settings and updates local state", async () => {
    mockedFetchResearchAiSettings.mockResolvedValueOnce({
      accountId: "paper_account_001",
      provider: "openai_compatible",
      model: "gpt-5.4",
      baseUrl: "https://api.openai.com/v1",
      hasApiKey: false,
      apiKeyHint: null,
      updatedAt: "2026-04-09T18:00:00+08:00",
    });
    mockedPutResearchAiSettings.mockResolvedValueOnce({
      accountId: "paper_account_001",
      provider: "openai_compatible",
      model: "gpt-5.4-mini",
      baseUrl: "https://saved-provider.test/v1",
      hasApiKey: true,
      apiKeyHint: "sk-...cret",
      updatedAt: "2026-04-09T18:05:00+08:00",
    });

    const { result } = renderHook(() => useAiResearchSettings({ enabled: true }));

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    await act(async () => {
      await result.current.save({
        provider: "openai_compatible",
        model: "gpt-5.4-mini",
        baseUrl: "https://saved-provider.test/v1",
        apiKey: "sk-saved-secret",
      });
    });

    expect(result.current.settings?.model).toBe("gpt-5.4-mini");
    expect(result.current.settings?.hasApiKey).toBe(true);
    expect(mockedPutResearchAiSettings).toHaveBeenCalledWith({
      provider: "openai_compatible",
      model: "gpt-5.4-mini",
      baseUrl: "https://saved-provider.test/v1",
      apiKey: "sk-saved-secret",
    });
  });
});
