import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  AI_RESEARCH_REQUEST_TIMEOUT_MS,
  AI_RESEARCH_REQUEST_TIMEOUT_PER_DECISION_MS,
  DEFAULT_AI_RESEARCH_PREVIEW_LIMIT,
  DEFAULT_AI_RESEARCH_LOOKBACK_BARS,
  fetchBalanceSummary,
  fetchResearchAiSettings,
  fetchFillHistory,
  fetchMarketBars,
  fetchOrderHistory,
  fetchReplayEvents,
  fetchResearchSnapshot,
  fetchRuntimeBars,
  fetchSharedContracts,
  inspectSymbol,
  submitRuntimeSymbolRequest,
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

  it("loads the shared contract catalog from the dedicated endpoint", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          contract_version: "v2.phase0.2026-04-11",
          phase: "phase_0",
          generated_from: {
            endpoint: "/v1/contracts/shared",
            config_entrypoint: "src.config.get_settings",
          },
          planes: [],
          naming_conventions: {
            operational_api_payloads: "snake_case",
            research_snapshot_payload: "camelCase",
            mcp_tool_names: "verb_phrases_with_snake_case",
            canonical_fact_ids: [],
            compatibility_rule: "compat",
          },
          symbol_layer_contract: {
            layer_order: ["observed", "supported", "runtime_enabled"],
            layers: [],
            transition_rules: [],
            current_boundaries: {
              supported_symbols: ["600036.SH"],
              runtime_symbols: ["600036.SH"],
              runtime_subset_of_supported: true,
            },
            current_supported_entries: [],
            examples: [],
          },
          fact_contracts: {},
          reason_code_catalog: {},
          naming_differences_audit: [],
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await fetchSharedContracts();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/contracts/shared",
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
          effective_scope: "strategy_submission",
          message: "Strategy paused.",
          reason_code: "OPERATOR_REQUEST",
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

  it("builds symbol inspection queries from the raw input", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          raw_input: "600036.sh",
          normalized_symbol: "600036.SH",
          format_valid: true,
          market: "a_share",
          market_label: "A 股",
          venue: "SH",
          venue_label: "上海证券交易所",
          display_name: "招商银行",
          name_status: "available",
          layers: {
            observed: true,
            supported: true,
            runtime_enabled: true,
          },
          reason_code: "SYMBOL_RUNTIME_ENABLED",
          message: "该股票代码已进入当前 trader 运行范围，可能影响自动交易判断。",
          runtime_activation: {
            requires_confirmation: true,
            phase: "phase_2_runtime_request",
            can_apply_now: false,
            effective_scope: "runtime_symbols",
            activation_mode: "already_live",
            request_status: "already_enabled",
            last_requested_at: null,
            requested_runtime_symbols_preview: ["600036.SH"],
            message: "该股票代码已在当前 runtime 范围内，无需再次申请。",
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await inspectSymbol("600036.sh");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/symbols/inspect?symbol=600036.sh",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
        },
      }),
    );
  });

  it("loads the balance summary from the dedicated endpoint", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          account_id: "paper_account_001",
          cash_balance: "98000",
          available_cash: "97500",
          frozen_cash: "500",
          market_value: "11850",
          equity: "109850",
          unrealized_pnl: "90",
          realized_pnl: "0",
          position_count: 1,
          cash_as_of_time: "2026-04-02T10:03:00+08:00",
          positions_as_of_time: "2026-04-02T10:00:00+08:00",
          as_of_time: "2026-04-02T10:03:00+08:00",
          summary_message: "账户权益由现金余额和持仓市值共同组成。",
          cash_explanation: "cash",
          position_explanation: "position",
          equity_explanation: "equity",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await fetchBalanceSummary();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/balance/summary",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
        },
      }),
    );
  });

  it("posts runtime-symbol requests as JSON", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          accepted: true,
          symbol: "000001.SZ",
          normalized_symbol: "000001.SZ",
          control_state: "normal",
          trader_run_id: null,
          instance_id: null,
          effective_at: "2026-04-11T10:10:00+08:00",
          effective_scope: "runtime_symbols",
          activation_mode: "requires_reload",
          request_status: "pending_reload",
          message: "已记录运行范围变更请求；需要重载 trader 后才会真正进入运行范围。",
          reason_code: "RUNTIME_CHANGE_REQUIRES_RELOAD",
          current_runtime_symbols: ["600036.SH"],
          requested_runtime_symbols: ["600036.SH", "000001.SZ"],
          last_requested_at: "2026-04-11T10:10:00+08:00",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await submitRuntimeSymbolRequest({
      symbol: "000001.SZ",
      confirm: true,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/symbols/runtime-requests",
      expect.objectContaining({
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          symbol: "000001.SZ",
          confirm: true,
        }),
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
      mode: "evaluation",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/research/snapshot?symbol=600036.SH&timeframe=15m&limit=48&mode=evaluation",
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
