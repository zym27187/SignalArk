import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useMarketData } from "./use-market-data";
import { fetchEquityCurve, fetchMarketBars, fetchRuntimeBars } from "../lib/api";

vi.mock("../lib/api", () => ({
  fetchMarketBars: vi.fn(),
  fetchEquityCurve: vi.fn(),
  fetchRuntimeBars: vi.fn(),
}));

const mockedFetchMarketBars = vi.mocked(fetchMarketBars);
const mockedFetchEquityCurve = vi.mocked(fetchEquityCurve);
const mockedFetchRuntimeBars = vi.mocked(fetchRuntimeBars);

describe("useMarketData", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  it("loads live market snapshots and preserves previous bars on partial refresh failures", async () => {
    const initialBars = [
      {
        time: "2026-04-02T10:00:00+08:00",
        open: 39.4,
        high: 39.6,
        low: 39.3,
        close: 39.5,
        volume: 120000,
      },
    ];
    const initialCurve = [{ time: "2026-04-02T10:00:00+08:00", value: 100000 }];
    const refreshedCurve = [{ time: "2026-04-02T10:15:00+08:00", value: 100120 }];
    const initialRuntimeBars = {
      filters: {},
      source: "trader_runtime_status",
      trader_run_id: "run-001",
      instance_id: "instance-A",
      lifecycle_status: "running",
      health_status: "alive",
      readiness_status: "ready",
      updated_at: "2026-04-02T10:00:02+08:00",
      count: { last_seen: 1, last_strategy: 1 },
      available_streams: [
        {
          stream_key: "cn_equity:600036.SH:15m",
          symbol: "600036.SH",
          timeframe: "15m",
          exchange: "cn_equity",
          last_seen_event_time: "2026-04-02T10:00:00+08:00",
          last_strategy_event_time: "2026-04-02T10:00:00+08:00",
        },
      ],
      last_seen_bars: [
        {
          stream_key: "cn_equity:600036.SH:15m",
          bar_key: "cn_equity:600036.SH:15m:2026-04-02T09:45:00+08:00",
          exchange: "cn_equity",
          symbol: "600036.SH",
          timeframe: "15m",
          bar_start_time: "2026-04-02T09:45:00+08:00",
          bar_end_time: "2026-04-02T10:00:00+08:00",
          event_time: "2026-04-02T10:00:00+08:00",
          ingest_time: "2026-04-02T10:00:02+08:00",
          open: 39.4,
          high: 39.6,
          low: 39.3,
          close: 39.5,
          volume: 120000,
          quote_volume: null,
          trade_count: null,
          closed: true,
          final: true,
          source_kind: "realtime",
          trade_date: "2026-04-02",
          trading_phase: "CONTINUOUS_AUCTION",
        },
      ],
      last_strategy_bars: [
        {
          stream_key: "cn_equity:600036.SH:15m",
          bar_key: "cn_equity:600036.SH:15m:2026-04-02T09:45:00+08:00",
          exchange: "cn_equity",
          symbol: "600036.SH",
          timeframe: "15m",
          bar_start_time: "2026-04-02T09:45:00+08:00",
          bar_end_time: "2026-04-02T10:00:00+08:00",
          event_time: "2026-04-02T10:00:00+08:00",
          ingest_time: "2026-04-02T10:00:02+08:00",
          open: 39.4,
          high: 39.6,
          low: 39.3,
          close: 39.5,
          volume: 120000,
          quote_volume: null,
          trade_count: null,
          closed: true,
          final: true,
          source_kind: "realtime",
          trade_date: "2026-04-02",
          trading_phase: "CONTINUOUS_AUCTION",
        },
      ],
      degraded_mode: {
        status: "normal",
        reason_code: "LIVE_DATA_READY",
        message: "当前系统使用真实数据，关键诊断状态没有发现明显降级。",
        data_source: "eastmoney",
        effective_at: "2026-04-02T10:00:02+08:00",
        impact: "runtime bars、replay events 和控制状态可以作为当前值守判断的主要依据。",
        suggested_action: "继续查看控制台即可。",
      },
    };

    mockedFetchMarketBars
      .mockResolvedValueOnce({
        symbol: "600036.SH",
        timeframe: "15m",
        count: 1,
        source: "live",
        bars: initialBars,
      })
      .mockRejectedValueOnce(new Error("bars temporarily unavailable"));
    mockedFetchEquityCurve
      .mockResolvedValueOnce({
        account_id: "paper_account_001",
        symbol: "600036.SH",
        timeframe: "15m",
        count: 1,
        source: "live",
        points: initialCurve,
      })
      .mockResolvedValueOnce({
        account_id: "paper_account_001",
        symbol: "600036.SH",
        timeframe: "15m",
        count: 1,
        source: "live",
        points: refreshedCurve,
      });
    mockedFetchRuntimeBars
      .mockResolvedValueOnce(initialRuntimeBars)
      .mockRejectedValueOnce(new Error("runtime bars temporarily unavailable"));

    const { result } = renderHook(() =>
      useMarketData({
        enabled: true,
        symbol: "600036.SH",
        timeframe: "15m",
      }),
    );

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.snapshot.bars).toEqual(initialBars);
    expect(result.current.snapshot.equityCurve).toEqual(initialCurve);
    expect(result.current.snapshot.runtimeBars).toEqual(initialRuntimeBars);

    await act(async () => {
      await result.current.refresh();
    });

    await waitFor(() => {
      expect(result.current.isRefreshing).toBe(false);
    });

    expect(result.current.snapshot.bars).toEqual(initialBars);
    expect(result.current.snapshot.equityCurve).toEqual(refreshedCurve);
    expect(result.current.snapshot.runtimeBars).toEqual(initialRuntimeBars);
    expect(result.current.snapshot.sectionErrors.bars).toBe("bars temporarily unavailable");
    expect(result.current.snapshot.sectionErrors.equityCurve).toBeUndefined();
    expect(result.current.snapshot.sectionErrors.runtimeBars).toBe(
      "runtime bars temporarily unavailable",
    );
  });

  it("skips network requests when the market view is disabled", () => {
    const { result } = renderHook(() =>
      useMarketData({
        enabled: false,
        symbol: "600036.SH",
        timeframe: "15m",
      }),
    );

    expect(result.current.isLoading).toBe(false);
    expect(mockedFetchMarketBars).not.toHaveBeenCalled();
    expect(mockedFetchEquityCurve).not.toHaveBeenCalled();
    expect(mockedFetchRuntimeBars).not.toHaveBeenCalled();
  });
});
