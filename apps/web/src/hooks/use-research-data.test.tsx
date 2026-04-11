import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useResearchData } from "./use-research-data";
import { fetchResearchSnapshot } from "../lib/api";
import { DEFAULT_RESEARCH_EVALUATION_LIMIT } from "../lib/api";

vi.mock("../lib/api", () => ({
  DEFAULT_RESEARCH_PREVIEW_LIMIT: 96,
  DEFAULT_RESEARCH_EVALUATION_LIMIT: 240,
  fetchResearchSnapshot: vi.fn(),
}));

const mockedFetchResearchSnapshot = vi.mocked(fetchResearchSnapshot);

describe("useResearchData", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  it("loads live research snapshots and preserves the previous payload on refresh failures", async () => {
    const initialSnapshot = {
      datasetName: "cn_equity / 600036.SH / 15m",
      sourceLabel: "由 research API 生成的真实回测结果",
      sourceMode: "live" as const,
      mode: "evaluation" as const,
      summary: {
        mode: "evaluation" as const,
        modeLabel: "评估样本",
        resultHeadline: "净收益 99.00，最大回撤 0.0000% ，交易 1 次。",
        sampleMessage: "评估样本说明",
        comparisonMessage: null,
      },
      klineBars: [
        {
          time: "2026-04-02T10:00:00+08:00",
          open: 39.4,
          high: 39.6,
          low: 39.3,
          close: 39.5,
          volume: 120000,
        },
      ],
      equityCurve: [
        { time: "2026-04-02T10:00:00+08:00", value: 100000, baseline: 100000 },
      ],
      manifest: {
        runId: "run-001",
        accountId: "paper_account_001",
        strategyId: "baseline_momentum_v1",
        strategyVersion: "baseline_momentum_v1",
        handlerName: "BaselineMomentumStrategy",
        description: "research snapshot",
        mode: "evaluation" as const,
        samplePurpose: "evaluation" as const,
        symbol: "600036.SH",
        symbols: ["600036.SH"],
        timeframe: "15m",
        barCount: 1,
        startTime: "2026-04-02T10:00:00+08:00",
        endTime: "2026-04-02T10:00:00+08:00",
        generatedAt: "2026-04-02T10:00:01+08:00",
        initialCash: 100000,
        costModel: "ashare_paper_cost_model",
        slippageBps: 5,
        feeModel: "ashare_paper_cost_model",
        slippageModel: "bar_close_bps",
        parameterSnapshot: {
          target_position: "400",
        },
        dataFingerprint: "bars:600036.SH:15m",
        manifestFingerprint: "manifest:run-001",
      },
      performance: {
        barCount: 1,
        signalCount: 1,
        orderCount: 1,
        tradeCount: 1,
        fillCount: 1,
        winningTradeCount: 1,
        losingTradeCount: 0,
        startingCash: 100000,
        endingCash: 99999,
        endingMarketValue: 100,
        startingEquity: 100000,
        endingEquity: 100099,
        netPnl: 99,
        totalReturnPct: 0.099,
        maxDrawdownPct: 0,
        realizedPnl: 0,
        unrealizedPnl: 99,
        turnover: 3950,
        winRatePct: 100,
      },
      decisions: [],
      experiments: null,
      comparison: null,
      notes: ["research API note"],
    };

    mockedFetchResearchSnapshot
      .mockResolvedValueOnce(initialSnapshot)
      .mockRejectedValueOnce(new Error("research snapshot unavailable"));

    const { result } = renderHook(() =>
      useResearchData({
        enabled: true,
        symbol: "600036.SH",
        timeframe: "15m",
        mode: "evaluation",
      }),
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(mockedFetchResearchSnapshot).toHaveBeenCalledWith({
      symbol: "600036.SH",
      timeframe: "15m",
      limit: DEFAULT_RESEARCH_EVALUATION_LIMIT,
      mode: "evaluation",
    });
    expect(result.current.snapshot).toEqual(initialSnapshot);
    expect(result.current.error).toBeNull();

    await act(async () => {
      await result.current.refresh();
    });

    await waitFor(() => {
      expect(result.current.isRefreshing).toBe(false);
    });

    expect(result.current.snapshot).toEqual(initialSnapshot);
    expect(result.current.error).toBe("research snapshot unavailable");
  });

  it("skips network requests when the research view is disabled", () => {
    const { result } = renderHook(() =>
      useResearchData({
        enabled: false,
        symbol: "600036.SH",
        timeframe: "15m",
        mode: "evaluation",
      }),
    );

    expect(result.current.isLoading).toBe(false);
    expect(mockedFetchResearchSnapshot).not.toHaveBeenCalled();
  });
});
