import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useRuleResearchData } from "./use-rule-research-data";
import { postResearchRuleSnapshot } from "../lib/api";

vi.mock("../lib/api", () => ({
  postResearchRuleSnapshot: vi.fn(),
}));

const mockedPostResearchRuleSnapshot = vi.mocked(postResearchRuleSnapshot);

describe("useRuleResearchData", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  it("runs rule research snapshots on demand and keeps the previous result on failures", async () => {
    const initialSnapshot = {
      datasetName: "cn_equity / 600036.SH / 1d",
      sourceLabel: "由 research API 生成的规则回测结果",
      sourceMode: "live" as const,
      mode: "evaluation" as const,
      summary: {
        mode: "evaluation" as const,
        modeLabel: "评估样本",
        resultHeadline: "净收益 320.00，最大回撤 4.1000% ，交易 2 次。",
        sampleMessage: "规则评估样本说明",
        comparisonMessage: null,
      },
      klineBars: [],
      equityCurve: [{ time: "2026-04-02T10:00:00+08:00", value: 100320, baseline: 100000 }],
      manifest: {
        runId: "run-rule-001",
        accountId: "paper_account_001",
        strategyId: "moving_average_band_v1",
        strategyVersion: "moving_average_band_v1",
        handlerName: "MovingAverageBandStrategy",
        description: "rule snapshot",
        mode: "evaluation" as const,
        samplePurpose: "evaluation" as const,
        symbol: "600036.SH",
        symbols: ["600036.SH"],
        timeframe: "1d",
        barCount: 750,
        startTime: "2023-04-02T10:00:00+08:00",
        endTime: "2026-04-02T10:00:00+08:00",
        generatedAt: "2026-04-02T10:00:01+08:00",
        initialCash: 100000,
        costModel: "ashare_paper_cost_model",
        slippageBps: 5,
        feeModel: "ashare_paper_cost_model",
        slippageModel: "bar_close_bps",
        parameterSnapshot: {
          rule_template: "moving_average_band_v1",
          ma_window: "60",
          target_position: "400",
        },
        dataFingerprint: "bars:600036.SH:1d",
        manifestFingerprint: "manifest:run-rule-001",
      },
      performance: {
        barCount: 750,
        signalCount: 2,
        orderCount: 2,
        tradeCount: 2,
        fillCount: 2,
        winningTradeCount: 1,
        losingTradeCount: 0,
        startingCash: 100000,
        endingCash: 99820,
        endingMarketValue: 500,
        startingEquity: 100000,
        endingEquity: 100320,
        netPnl: 320,
        totalReturnPct: 0.32,
        maxDrawdownPct: 4.1,
        realizedPnl: 120,
        unrealizedPnl: 200,
        turnover: 78000,
        winRatePct: 100,
      },
      decisions: [],
      experiments: null,
      comparison: null,
      notes: ["rule note"],
    };

    mockedPostResearchRuleSnapshot
      .mockResolvedValueOnce(initialSnapshot)
      .mockRejectedValueOnce(new Error("rule snapshot unavailable"));

    const { result } = renderHook(() => useRuleResearchData());

    await act(async () => {
      await result.current.run({
        symbol: "600036.SH",
        timeframe: "1d",
        limit: 750,
        ruleTemplate: "moving_average_band_v1",
        ruleConfig: {
          maWindow: 60,
          buyBelowMaPct: 0.05,
          sellAboveMaPct: 0.1,
          targetPosition: 400,
        },
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
    expect(result.current.error).toBe("rule snapshot unavailable");
  });

  it("resets rule research state explicitly", async () => {
    mockedPostResearchRuleSnapshot.mockResolvedValueOnce({
      datasetName: "test",
      sourceLabel: "rule",
      sourceMode: "live",
      mode: "evaluation",
      summary: {
        mode: "evaluation",
        modeLabel: "评估样本",
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

    const { result } = renderHook(() => useRuleResearchData());

    await act(async () => {
      await result.current.run({
        timeframe: "1d",
        ruleTemplate: "moving_average_band_v1",
        ruleConfig: {
          maWindow: 60,
          buyBelowMaPct: 0.05,
          sellAboveMaPct: 0.1,
          targetPosition: 400,
        },
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
