import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  fetchFillHistory,
  fetchMarketBars,
  fetchOrderHistory,
  fetchReplayEvents,
  fetchResearchSnapshot,
  fetchStatus,
  postControlAction,
} from "./api";

describe("api helpers", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("builds market-bar queries from symbol, timeframe, and limit", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          symbol: "600036.SH",
          timeframe: "1h",
          count: 1,
          source: "test",
          bars: [],
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await fetchMarketBars({
      symbol: "600036.SH",
      timeframe: "1h",
      limit: 12,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/market/bars?symbol=600036.SH&timeframe=1h&limit=12",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
        },
      }),
    );
  });

  it("posts control actions with the expected endpoint and method", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          accepted: true,
          control_state: "strategy_paused",
          trader_run_id: null,
          instance_id: null,
          effective_at: "2026-04-02T10:00:00+08:00",
          message: "Strategy paused.",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await postControlAction("pauseStrategy");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/controls/strategy/pause",
      expect.objectContaining({
        method: "POST",
      }),
    );
  });

  it("builds execution-history queries from shared filters", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          filters: {},
          count: 0,
          orders: [],
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await fetchOrderHistory({
      symbol: "600036.SH",
      traderRunId: "run-001",
      startTime: "2026-04-02T02:00:00.000Z",
      endTime: "2026-04-02T03:00:00.000Z",
      status: "FILLED",
      limit: 25,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/orders/history?symbol=600036.SH&trader_run_id=run-001&start_time=2026-04-02T02%3A00%3A00.000Z&end_time=2026-04-02T03%3A00%3A00.000Z&status=FILLED&limit=25",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
        },
      }),
    );
  });

  it("builds fill-history and replay queries from shared filters", async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            filters: {},
            count: 0,
            fills: [],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            filters: {},
            count: 0,
            events: [],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );

    await fetchFillHistory({
      symbol: "600036.SH",
      traderRunId: "run-001",
      orderId: "order-001",
      limit: 20,
    });
    await fetchReplayEvents({
      symbol: "600036.SH",
      traderRunId: "run-001",
      limit: 20,
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8000/v1/fills/history?symbol=600036.SH&trader_run_id=run-001&order_id=order-001&limit=20",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
        },
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8000/v1/diagnostics/replay-events?symbol=600036.SH&trader_run_id=run-001&limit=20",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
        },
      }),
    );
  });

  it("builds research snapshot queries from symbol, timeframe, and limit", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          datasetName: "cn_equity / 600036.SH / 15m",
          sourceLabel: "由 research API 生成的真实回测结果",
          sourceMode: "live",
          klineBars: [],
          runtimePnlCurve: [],
          backtestEquityCurve: [],
          manifest: {},
          performance: {},
          decisions: [],
          notes: [],
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await fetchResearchSnapshot({
      symbol: "600036.SH",
      timeframe: "15m",
      limit: 48,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/research/snapshot?symbol=600036.SH&timeframe=15m&limit=48",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
        },
      }),
    );
  });

  it("localizes API error details before surfacing them", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: "Request failed with status 503.",
        }),
        {
          status: 503,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await expect(fetchStatus()).rejects.toMatchObject({
      message: "请求失败，状态码 503。",
      status: 503,
    });
  });
});
