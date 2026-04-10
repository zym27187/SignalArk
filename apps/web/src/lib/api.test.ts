import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  AI_RESEARCH_REQUEST_TIMEOUT_MS,
  AI_RESEARCH_REQUEST_TIMEOUT_PER_DECISION_MS,
  DEFAULT_AI_RESEARCH_PREVIEW_LIMIT,
  DEFAULT_AI_RESEARCH_LOOKBACK_BARS,
  fetchResearchAiSettings,
  fetchFillHistory,
  fetchMarketBars,
  fetchOrderHistory,
  fetchReplayEvents,
  fetchResearchSnapshot,
  fetchRuntimeBars,
  resolveAiResearchRequestTimeoutMs,
  fetchStatus,
  postControlAction,
  postResearchAiSnapshot,
  putResearchAiSettings,
} from "./api";

describe("api helpers", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    vi.useRealTimers();
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

  it("builds runtime-bar audit queries from symbol and timeframe", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          filters: {},
          source: "trader_runtime_status",
          trader_run_id: "run-001",
          instance_id: "instance-A",
          lifecycle_status: "running",
          health_status: "alive",
          readiness_status: "ready",
          updated_at: "2026-04-03T09:45:00+08:00",
          count: { last_seen: 1, last_strategy: 1 },
          available_streams: [],
          last_seen_bars: [],
          last_strategy_bars: [],
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await fetchRuntimeBars({
      symbol: "600036.SH",
      timeframe: "15m",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/market/runtime-bars?symbol=600036.SH&timeframe=15m",
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
          equityCurve: [],
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

  it("posts AI research snapshot requests as JSON", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          datasetName: "cn_equity / 600036.SH / 15m",
          sourceLabel: "由 research API 生成的 AI 回测结果",
          sourceMode: "live",
          klineBars: [],
          equityCurve: [],
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

    await postResearchAiSnapshot({
      symbol: "600036.SH",
      timeframe: "15m",
      limit: 48,
      provider: "openai_compatible",
      model: "gpt-5.4",
      baseUrl: "https://api.openai.com/v1",
      apiKey: "sk-test",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/research/ai-snapshot",
      expect.objectContaining({
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          symbol: "600036.SH",
          timeframe: "15m",
          limit: 48,
          provider: "openai_compatible",
          model: "gpt-5.4",
          baseUrl: "https://api.openai.com/v1",
          apiKey: "sk-test",
        }),
      }),
    );
  });

  it("uses the AI preview default limit when none is provided", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          datasetName: "cn_equity / 600036.SH / 15m",
          sourceLabel: "由 research API 生成的 AI 回测结果",
          sourceMode: "live",
          klineBars: [],
          equityCurve: [],
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

    await postResearchAiSnapshot({
      symbol: "600036.SH",
      timeframe: "15m",
      provider: "openai_compatible",
      model: "gpt-5.4",
      baseUrl: "https://api.openai.com/v1",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/research/ai-snapshot",
      expect.objectContaining({
        body: JSON.stringify({
          symbol: "600036.SH",
          timeframe: "15m",
          limit: DEFAULT_AI_RESEARCH_PREVIEW_LIMIT,
          provider: "openai_compatible",
          model: "gpt-5.4",
          baseUrl: "https://api.openai.com/v1",
        }),
      }),
    );
  });

  it("times out stalled AI research snapshot requests", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation((_input, init) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener(
          "abort",
          () => {
            reject(new DOMException("The operation was aborted.", "AbortError"));
          },
          { once: true },
        );
      });
    });

    const pendingExpectation = expect(
      postResearchAiSnapshot({
        provider: "openai_compatible",
        model: "gpt-5.4",
        baseUrl: "https://api.openai.com/v1",
      }),
    ).rejects.toMatchObject({
      message: "AI research request timed out.",
    });

    await vi.advanceTimersByTimeAsync(
      resolveAiResearchRequestTimeoutMs(DEFAULT_AI_RESEARCH_PREVIEW_LIMIT),
    );

    await pendingExpectation;
  });

  it("scales AI timeout with the preview window", () => {
    expect(resolveAiResearchRequestTimeoutMs(12)).toBe(AI_RESEARCH_REQUEST_TIMEOUT_MS);
    expect(resolveAiResearchRequestTimeoutMs(24)).toBe(
      10_000
        + (24 - DEFAULT_AI_RESEARCH_LOOKBACK_BARS + 1)
          * AI_RESEARCH_REQUEST_TIMEOUT_PER_DECISION_MS,
    );
  });

  it("loads and saves persisted AI research settings", async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            accountId: "paper_account_001",
            provider: "openai_compatible",
            model: "gpt-5.4",
            baseUrl: "https://api.openai.com/v1",
            hasApiKey: true,
            apiKeyHint: "sk-...cret",
            updatedAt: "2026-04-09T18:00:00+08:00",
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
            accountId: "paper_account_001",
            provider: "openai_compatible",
            model: "gpt-5.4-mini",
            baseUrl: "https://saved-provider.test/v1",
            hasApiKey: true,
            apiKeyHint: "sk-...cret",
            updatedAt: "2026-04-09T18:05:00+08:00",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );

    await fetchResearchAiSettings();
    await putResearchAiSettings({
      provider: "openai_compatible",
      model: "gpt-5.4-mini",
      baseUrl: "https://saved-provider.test/v1",
      apiKey: "sk-saved-secret",
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8000/v1/research/ai-settings",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
        },
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8000/v1/research/ai-settings",
      expect.objectContaining({
        method: "PUT",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          provider: "openai_compatible",
          model: "gpt-5.4-mini",
          baseUrl: "https://saved-provider.test/v1",
          apiKey: "sk-saved-secret",
          clearApiKey: false,
        }),
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

  it("localizes AI provider timeout details before surfacing them", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          detail:
            "AI provider request timed out after 15s while calling https://openai.test/v1/chat/completions.",
        }),
        {
          status: 502,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await expect(
      postResearchAiSnapshot({
        provider: "openai_compatible",
        model: "gpt-5.4",
        baseUrl: "https://openai.test/v1",
      }),
    ).rejects.toMatchObject({
      message: "AI 服务请求超时（15 秒）：https://openai.test/v1/chat/completions。",
      status: 502,
    });
  });
});
