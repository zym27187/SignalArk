import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchMarketBars, fetchStatus, postControlAction } from "./api";

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
