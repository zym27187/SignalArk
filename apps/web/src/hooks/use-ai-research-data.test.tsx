import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAiResearchData } from "./use-ai-research-data";
import { postResearchAiSnapshot } from "../lib/api";

vi.mock("../lib/api", () => ({
  postResearchAiSnapshot: vi.fn(),
}));

const mockedPostResearchAiSnapshot = vi.mocked(postResearchAiSnapshot);

describe("useAiResearchData", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  it("runs AI research snapshots on demand and keeps the previous result on failures", async () => {
    const initialSnapshot = {
      datasetName: "cn_equity / 600036.SH / 15m",
      sourceLabel: "由 research API 生成的 AI 回测结果",
      sourceMode: "live" as const,
      mode: "preview" as const,
      summary: {
        mode: "preview" as const,
        modeLabel: "快速预览",
        resultHeadline: "净收益 220.00，最大回撤 0.0300% ，交易 1 次。",
        sampleMessage: "AI 预览样本说明",
        comparisonMessage: null,
      },
      klineBars: [],
      equityCurve: [{ time: "2026-04-02T10:00:00+08:00", value: 100120, baseline: 100000 }],
      manifest: {
        runId: "run-ai-001",
        accountId: "paper_account_001",
        strategyId: "ai_bar_judge_v1",
        strategyVersion: "ai_bar_judge_v1",
        handlerName: "AiBarJudgeStrategy",
        description: "ai snapshot",
        mode: "preview" as const,
        samplePurpose: "preview" as const,
        symbol: "600036.SH",
        symbols: ["600036.SH"],
        timeframe: "15m",
        barCount: 12,
        startTime: "2026-04-02T10:00:00+08:00",
        endTime: "2026-04-02T12:45:00+08:00",
        generatedAt: "2026-04-02T12:45:01+08:00",
        initialCash: 100000,
        costModel: "ashare_paper_cost_model",
        slippageBps: 5,
        feeModel: "ashare_paper_cost_model",
        slippageModel: "bar_close_bps",
        parameterSnapshot: {},
        dataFingerprint: "bars:600036.SH:15m",
        manifestFingerprint: "manifest:run-ai-001",
      },
      performance: {
        barCount: 12,
        signalCount: 1,
        orderCount: 1,
        tradeCount: 1,
        fillCount: 1,
        winningTradeCount: 1,
        losingTradeCount: 0,
        startingCash: 100000,
        endingCash: 99850,
        endingMarketValue: 370,
        startingEquity: 100000,
        endingEquity: 100220,
        netPnl: 220,
        totalReturnPct: 0.22,
        maxDrawdownPct: 0.03,
        realizedPnl: 0,
        unrealizedPnl: 220,
        turnover: 3980,
        winRatePct: 100,
      },
      decisions: [],
      experiments: null,
      comparison: null,
      notes: ["ai note"],
    };

    mockedPostResearchAiSnapshot
      .mockResolvedValueOnce(initialSnapshot)
      .mockRejectedValueOnce(new Error("ai provider unavailable"));

    const { result } = renderHook(() => useAiResearchData());

    await act(async () => {
      await result.current.run({
        symbol: "600036.SH",
        timeframe: "15m",
        provider: "openai_compatible",
        model: "gpt-5.4",
        baseUrl: "https://api.openai.com/v1",
        apiKey: "sk-test",
      });
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.snapshot).toEqual(initialSnapshot);
    expect(result.current.error).toBeNull();

    await act(async () => {
      await result.current.refresh();
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.snapshot).toEqual(initialSnapshot);
    expect(result.current.error).toBe("ai provider unavailable");
  });

  it("resets AI research state explicitly", async () => {
    mockedPostResearchAiSnapshot.mockResolvedValueOnce({
      datasetName: "test",
      sourceLabel: "ai",
      sourceMode: "live",
      mode: "preview",
      summary: {
        mode: "preview",
        modeLabel: "快速预览",
        resultHeadline: "summary",
        sampleMessage: "sample",
        comparisonMessage: null,
      },
      klineBars: [],
      equityCurve: [],
      manifest: {} as never,
      performance: {} as never,
      decisions: [],
      experiments: null,
      comparison: null,
      notes: [],
    });

    const { result } = renderHook(() => useAiResearchData());

    await act(async () => {
      await result.current.run({
        provider: "heuristic_stub",
      });
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.snapshot).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.lastRequest).toBeNull();
  });
});
