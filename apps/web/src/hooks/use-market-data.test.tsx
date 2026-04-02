import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useMarketData } from "./use-market-data";
import { fetchEquityCurve, fetchMarketBars } from "../lib/api";

vi.mock("../lib/api", () => ({
  fetchMarketBars: vi.fn(),
  fetchEquityCurve: vi.fn(),
}));

const mockedFetchMarketBars = vi.mocked(fetchMarketBars);
const mockedFetchEquityCurve = vi.mocked(fetchEquityCurve);

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

    await act(async () => {
      await result.current.refresh();
    });

    await waitFor(() => {
      expect(result.current.isRefreshing).toBe(false);
    });

    expect(result.current.snapshot.bars).toEqual(initialBars);
    expect(result.current.snapshot.equityCurve).toEqual(refreshedCurve);
    expect(result.current.snapshot.sectionErrors.bars).toBe("bars temporarily unavailable");
    expect(result.current.snapshot.sectionErrors.equityCurve).toBeUndefined();
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
  });
});
