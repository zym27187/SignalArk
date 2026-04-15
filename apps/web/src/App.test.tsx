import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { DEFAULT_AI_RESEARCH_PREVIEW_LIMIT } from "./lib/api";
import { useAiResearchData } from "./hooks/use-ai-research-data";
import { useDashboardData } from "./hooks/use-dashboard-data";
import { useAiResearchSettings } from "./hooks/use-ai-research-settings";
import { useMarketData } from "./hooks/use-market-data";
import { useResearchData } from "./hooks/use-research-data";
import { useRuleResearchData } from "./hooks/use-rule-research-data";

vi.mock("./hooks/use-dashboard-data", () => ({
  useDashboardData: vi.fn(),
}));

vi.mock("./hooks/use-market-data", () => ({
  useMarketData: vi.fn(),
}));

vi.mock("./hooks/use-ai-research-settings", () => ({
  useAiResearchSettings: vi.fn(),
}));

vi.mock("./hooks/use-ai-research-data", () => ({
  useAiResearchData: vi.fn(),
}));

vi.mock("./hooks/use-research-data", () => ({
  useResearchData: vi.fn(),
}));

vi.mock("./hooks/use-rule-research-data", () => ({
  useRuleResearchData: vi.fn(),
}));

const mockedUseDashboardData = vi.mocked(useDashboardData);
const mockedUseAiResearchData = vi.mocked(useAiResearchData);
const mockedUseAiResearchSettings = vi.mocked(useAiResearchSettings);
const mockedUseMarketData = vi.mocked(useMarketData);
const mockedUseResearchData = vi.mocked(useResearchData);
const mockedUseRuleResearchData = vi.mocked(useRuleResearchData);

describe("App", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    mockedUseDashboardData.mockReturnValue({
      snapshot: {
        balanceSummary: {
          account_id: "paper_account_001",
          cash_balance: "98000",
          available_cash: "97500",
          frozen_cash: "500",
          market_value: "0",
          equity: "98000",
          unrealized_pnl: "0",
          realized_pnl: "0",
          position_count: 0,
          cash_as_of_time: "2026-04-02T10:00:00+08:00",
          positions_as_of_time: null,
          as_of_time: "2026-04-02T10:00:00+08:00",
          summary_message: "当前没有持仓，账户权益等于现金余额。",
          cash_explanation: "cash",
          position_explanation: "position",
          equity_explanation: "equity",
        },
        status: {
          trader_run_id: "run-001",
          instance_id: "instance-A",
          account_id: "paper_account_001",
          control_state: "normal",
          strategy_enabled: true,
          kill_switch_active: false,
          protection_mode_active: false,
          ready: true,
          status: "ready",
          health_status: "alive",
          lifecycle_status: "running",
          market_data_fresh: true,
          market_state_available: true,
          latest_final_bar_time: "2026-04-02T10:00:00+08:00",
          current_trading_phase: "CONTINUOUS_AUCTION",
          lease_owner_instance_id: "instance-A",
          lease_expires_at: "2026-04-02T10:00:15+08:00",
          last_heartbeat_at: "2026-04-02T10:00:05+08:00",
          fencing_token: 3,
          symbols: ["600036.SH", "000001.SZ"],
          symbol_names: {
            "600036.SH": "招商银行",
            "000001.SZ": "平安银行",
          },
          degraded_mode: {
            status: "normal",
            reason_code: "LIVE_DATA_READY",
            message: "当前系统使用真实数据，关键诊断状态没有发现明显降级。",
            data_source: "eastmoney",
            effective_at: "2026-04-02T10:00:00+08:00",
            impact: "runtime bars、replay events 和控制状态可以作为当前值守判断的主要依据。",
            suggested_action: "继续查看当前控制台即可。",
          },
        },
        positions: [],
        orders: [],
        orderHistory: [],
        fills: [],
        events: [],
        sectionErrors: {},
        fetchedAt: "2026-04-02T10:00:00+08:00",
      },
      isLoading: false,
      isRefreshing: false,
      pendingAction: null,
      lastActionResult: null,
      activityFilters: {
        symbol: "",
        status: "",
        orderId: "",
        traderRunId: "",
        startTime: "",
        endTime: "",
        limit: 12,
      },
      refresh: vi.fn(),
      applyActivityFilters: vi.fn(),
      resetActivityFilters: vi.fn(),
      performAction: vi.fn(),
    });
    mockedUseMarketData.mockImplementation(() => ({
      snapshot: {
        symbol: null,
        timeframe: null,
        bars: [],
        equityCurve: [],
        runtimeBars: {
          filters: {},
          source: "trader_runtime_status",
          trader_run_id: null,
          instance_id: null,
          lifecycle_status: null,
          health_status: null,
          readiness_status: null,
          updated_at: null,
          count: {
            last_seen: 0,
            last_strategy: 0,
          },
          available_streams: [],
          last_seen_bars: [],
          last_strategy_bars: [],
          degraded_mode: {
            status: "normal",
            reason_code: "LIVE_DATA_READY",
            message: "当前系统使用真实数据，关键诊断状态没有发现明显降级。",
            data_source: "eastmoney",
            effective_at: "2026-04-02T10:00:00+08:00",
            impact: "runtime bars、replay events 和控制状态可以作为当前值守判断的主要依据。",
            suggested_action: "继续查看当前控制台即可。",
          },
        },
        sectionErrors: {},
        fetchedAt: null,
      },
      isLoading: false,
      isRefreshing: false,
      refresh: vi.fn(),
    }));
    mockedUseResearchData.mockImplementation(() => ({
      snapshot: {
        datasetName: "cn_equity / 000001.SZ / 15m",
        sourceLabel: "由 research API 生成的真实回测结果",
        sourceMode: "live",
        mode: "evaluation",
        summary: {
          mode: "evaluation",
          modeLabel: "评估样本",
          resultHeadline: "净收益 99.00，最大回撤 0.0000% ，交易 1 次。",
          sampleMessage: "评估样本说明",
          comparisonMessage: null,
        },
        klineBars: [],
        equityCurve: [
          {
            time: "2026-04-02T10:00:00+08:00",
            value: 100000,
            baseline: 100000,
          },
        ],
        manifest: {
          runId: "run-001",
          accountId: "paper_account_001",
          strategyId: "baseline_momentum_v1",
          strategyVersion: "baseline_momentum_v1",
          handlerName: "BaselineMomentumStrategy",
          description: "Long-only threshold momentum against previous close.",
          mode: "evaluation",
          samplePurpose: "evaluation",
          symbol: "000001.SZ",
          symbols: ["000001.SZ"],
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
            entry_threshold_pct: "0.0005",
            exit_threshold_pct: "0",
            trend_lookback_bars: "3",
            min_trend_up_bars: "2",
            strong_entry_threshold_pct: "0.0012",
            reduced_target_ratio: "0.5",
            trailing_stop_pct: "0.01",
          },
          dataFingerprint: "bars:000001.SZ:15m",
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
      },
      error: null,
      fetchedAt: "2026-04-02T10:00:00+08:00",
      isLoading: false,
      isRefreshing: false,
      refresh: vi.fn(),
    }));
    mockedUseAiResearchSettings.mockReturnValue({
      settings: {
        accountId: "paper_account_001",
        provider: "openai_compatible",
        model: "gpt-5.4",
        baseUrl: "https://api.openai.com/v1",
        hasApiKey: true,
        apiKeyHint: "sk-...cret",
        updatedAt: "2026-04-02T10:00:00+08:00",
      },
      error: null,
      isLoading: false,
      isSaving: false,
      refresh: vi.fn(),
      save: vi.fn(),
    });
    mockedUseAiResearchData.mockReturnValue({
      snapshot: null,
      error: null,
      fetchedAt: null,
      isLoading: false,
      isRefreshing: false,
      lastRequest: null,
      run: vi.fn(),
      refresh: vi.fn(),
      reset: vi.fn(),
    });
    mockedUseRuleResearchData.mockReturnValue({
      snapshot: null,
      error: null,
      fetchedAt: null,
      isLoading: false,
      isRefreshing: false,
      lastRequest: null,
      run: vi.fn(),
      refresh: vi.fn(),
      reset: vi.fn(),
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shares the selected symbol across market and research views", async () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "股票代码管理" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "资金与权益" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "常见术语" })).toBeInTheDocument();

    expect(mockedUseMarketData).toHaveBeenLastCalledWith({
      enabled: false,
      symbol: "600036.SH",
      timeframe: "15m",
    });

    fireEvent.click(screen.getByRole("button", { name: /市场/ }));

    await waitFor(() => {
      expect(window.location.hash).toBe("#market");
    });
    expect(mockedUseMarketData).toHaveBeenLastCalledWith({
      enabled: true,
      symbol: "600036.SH",
      timeframe: "15m",
    });

    fireEvent.click(screen.getByRole("tab", { name: "平安银行 (000001.SZ)" }));

    await waitFor(() => {
      expect(mockedUseMarketData).toHaveBeenLastCalledWith({
        enabled: true,
        symbol: "000001.SZ",
        timeframe: "15m",
      });
    });

    fireEvent.click(screen.getByRole("tab", { name: "1h" }));

    await waitFor(() => {
      expect(mockedUseMarketData).toHaveBeenLastCalledWith({
        enabled: true,
        symbol: "000001.SZ",
        timeframe: "1h",
      });
    });

    fireEvent.click(screen.getByRole("button", { name: /研究/ }));

    await waitFor(() => {
      expect(window.location.hash).toBe("#research");
    });
    expect(mockedUseResearchData).toHaveBeenLastCalledWith({
      enabled: true,
      symbol: "000001.SZ",
      timeframe: "15m",
      mode: "evaluation",
    });
    expect(screen.getByText(/paper_account_001 \/ 平安银行 \(000001\.SZ\)/)).toBeInTheDocument();
    expect(screen.getByText("模型实验台")).toBeInTheDocument();
    expect(screen.getByText("这次回测怎么判断买卖")).toBeInTheDocument();
    expect(screen.getByText("只做多阈值动量")).toBeInTheDocument();
    expect(
      screen.getByText(/先观察最近 3 根 K 线，确认其中至少 2 次收盘上涨后/),
    ).toBeInTheDocument();
  });

  it("shows explicit degraded-mode guidance in the market view", async () => {
    mockedUseDashboardData.mockReturnValue({
      snapshot: {
        status: {
          trader_run_id: "run-001",
          instance_id: "instance-A",
          account_id: "paper_account_001",
          control_state: "normal",
          strategy_enabled: true,
          kill_switch_active: false,
          protection_mode_active: false,
          ready: false,
          status: "not_ready",
          health_status: "alive",
          lifecycle_status: "running",
          market_data_fresh: false,
          market_state_available: true,
          latest_final_bar_time: null,
          current_trading_phase: "CONTINUOUS_AUCTION",
          lease_owner_instance_id: "instance-A",
          lease_expires_at: "2026-04-02T10:00:15+08:00",
          last_heartbeat_at: "2026-04-02T10:00:05+08:00",
          fencing_token: 3,
          env: "dev",
          execution_mode: "paper",
          exchange: "cn_equity",
          symbols: ["600036.SH", "000001.SZ"],
          symbol_names: {
            "600036.SH": "招商银行",
            "000001.SZ": "平安银行",
          },
          degraded_mode: {
            status: "fixture",
            reason_code: "FIXTURE_DATA_IN_USE",
            message: "当前系统正在使用 fixture 行情，诊断和价格只适合演练，不应视为真实市场。",
            data_source: "fixture",
            effective_at: "2026-04-02T10:00:00+08:00",
            impact: "你看到的价格、runtime audit 和后续判断都基于示例数据，不适合据此判断真实盘中状态。",
            suggested_action: "如需确认真实市场状态，请切回 eastmoney 数据源后再查看控制台。",
          },
        },
        positions: [],
        orders: [],
        orderHistory: [],
        fills: [],
        events: [],
        sectionErrors: {},
        fetchedAt: "2026-04-02T10:00:00+08:00",
        balanceSummary: {
          account_id: "paper_account_001",
          cash_balance: "98000",
          available_cash: "97500",
          frozen_cash: "500",
          market_value: "0",
          equity: "98000",
          unrealized_pnl: "0",
          realized_pnl: "0",
          position_count: 0,
          cash_as_of_time: "2026-04-02T10:00:00+08:00",
          positions_as_of_time: null,
          as_of_time: "2026-04-02T10:00:00+08:00",
          summary_message: "当前没有持仓，账户权益等于现金余额。",
          cash_explanation: "cash",
          position_explanation: "position",
          equity_explanation: "equity",
        },
      },
      isLoading: false,
      isRefreshing: false,
      pendingAction: null,
      lastActionResult: null,
      activityFilters: {
        symbol: "",
        status: "",
        orderId: "",
        traderRunId: "",
        startTime: "",
        endTime: "",
        limit: 12,
      },
      refresh: vi.fn(),
      applyActivityFilters: vi.fn(),
      resetActivityFilters: vi.fn(),
      performAction: vi.fn(),
    });
    mockedUseMarketData.mockImplementation(() => ({
      snapshot: {
        symbol: null,
        timeframe: null,
        bars: [],
        equityCurve: [],
        runtimeBars: {
          filters: {},
          source: "trader_runtime_status",
          trader_run_id: null,
          instance_id: null,
          lifecycle_status: null,
          health_status: null,
          readiness_status: null,
          updated_at: null,
          count: {
            last_seen: 0,
            last_strategy: 0,
          },
          available_streams: [],
          last_seen_bars: [],
          last_strategy_bars: [],
          degraded_mode: {
            status: "fixture",
            reason_code: "FIXTURE_DATA_IN_USE",
            message: "当前系统正在使用 fixture 行情，诊断和价格只适合演练，不应视为真实市场。",
            data_source: "fixture",
            effective_at: "2026-04-02T10:00:00+08:00",
            impact: "你看到的价格、runtime audit 和后续判断都基于示例数据，不适合据此判断真实盘中状态。",
            suggested_action: "如需确认真实市场状态，请切回 eastmoney 数据源后再查看控制台。",
          },
        },
        sectionErrors: {},
        fetchedAt: null,
      },
      isLoading: false,
      isRefreshing: false,
      refresh: vi.fn(),
    }));

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /市场/ }));

    await waitFor(() => {
      expect(window.location.hash).toBe("#market");
    });

    expect(screen.getByText("当前系统正在使用 fixture 行情，诊断和价格只适合演练，不应视为真实市场。")).toBeInTheDocument();
    expect(screen.getByText(/如需确认真实市场状态，请切回 eastmoney 数据源后再查看控制台。/)).toBeInTheDocument();
  });

  it("switches baseline research between evaluation and preview modes", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /研究/ }));

    await waitFor(() => {
      expect(window.location.hash).toBe("#research");
    });

    expect(mockedUseResearchData).toHaveBeenLastCalledWith({
      enabled: true,
      symbol: "600036.SH",
      timeframe: "15m",
      mode: "evaluation",
    });

    fireEvent.click(screen.getByRole("button", { name: /快速预览/i }));

    await waitFor(() => {
      expect(mockedUseResearchData).toHaveBeenLastCalledWith({
        enabled: true,
        symbol: "600036.SH",
        timeframe: "15m",
        mode: "preview",
      });
    });
  });

  it("offers 1d research timeframe and rule lookback presets", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /研究/ }));

    await waitFor(() => {
      expect(window.location.hash).toBe("#research");
    });

    expect(screen.getByRole("tab", { name: "1d" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1 年" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "3 年" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "5 年" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "1d" }));

    await waitFor(() => {
      expect(mockedUseResearchData).toHaveBeenLastCalledWith({
        enabled: true,
        symbol: "600036.SH",
        timeframe: "1d",
        mode: "evaluation",
      });
    });

    fireEvent.click(screen.getByRole("button", { name: "5 年" }));

    expect(screen.getByText(/5 年约 1250 根 bar/)).toBeInTheDocument();
  });

  it("runs AI research with the fast preview limit from the research view", async () => {
    const saveMock = vi.fn().mockResolvedValue({
      accountId: "paper_account_001",
      provider: "openai_compatible",
      model: "gpt-5.4",
      baseUrl: "https://api.openai.com/v1",
      hasApiKey: true,
      apiKeyHint: "sk-...cret",
      updatedAt: "2026-04-02T10:05:00+08:00",
    });
    const runMock = vi.fn().mockResolvedValue(null);
    mockedUseAiResearchSettings.mockReturnValue({
      settings: {
        accountId: "paper_account_001",
        provider: "openai_compatible",
        model: "gpt-5.4",
        baseUrl: "https://api.openai.com/v1",
        hasApiKey: true,
        apiKeyHint: "sk-...cret",
        updatedAt: "2026-04-02T10:00:00+08:00",
      },
      error: null,
      isLoading: false,
      isSaving: false,
      refresh: vi.fn(),
      save: saveMock,
    });
    mockedUseAiResearchData.mockReturnValue({
      snapshot: null,
      error: null,
      fetchedAt: null,
      isLoading: false,
      isRefreshing: false,
      lastRequest: null,
      run: runMock,
      refresh: vi.fn(),
      reset: vi.fn(),
    });

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /研究/ }));

    await waitFor(() => {
      expect(window.location.hash).toBe("#research");
    });

    expect(
      screen.getByText(`快速预览最近 ${DEFAULT_AI_RESEARCH_PREVIEW_LIMIT} 根 K 线`),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "保存并运行 AI 回测" }));

    await waitFor(() => {
      expect(saveMock).toHaveBeenCalled();
      expect(runMock).toHaveBeenCalledWith({
        symbol: "600036.SH",
        timeframe: "15m",
        limit: DEFAULT_AI_RESEARCH_PREVIEW_LIMIT,
        provider: "openai_compatible",
        model: "gpt-5.4",
        baseUrl: "https://api.openai.com/v1",
      });
    });
  });

  it("runs rule research from the quick-fill button with the current symbol and years", async () => {
    const runMock = vi.fn().mockResolvedValue({
      datasetName: "cn_equity / 600036.SH / 1d",
      sourceLabel: "由 research API 生成的规则回测结果",
      sourceMode: "live",
      mode: "evaluation",
      summary: {
        mode: "evaluation",
        modeLabel: "评估样本",
        resultHeadline: "净收益 320.00，最大回撤 4.1000% ，交易 2 次。",
        sampleMessage: "规则评估样本说明",
        comparisonMessage: null,
      },
      klineBars: [],
      equityCurve: [],
      manifest: {
        runId: "rule-run-001",
        accountId: "paper_account_001",
        strategyId: "moving_average_band_v1",
        strategyVersion: "moving_average_band_v1",
        handlerName: "MovingAverageBandStrategy",
        description: "rule snapshot",
        mode: "evaluation",
        samplePurpose: "evaluation",
        symbol: "600036.SH",
        symbols: ["600036.SH"],
        timeframe: "1d",
        barCount: 1250,
        startTime: "2021-04-02T10:00:00+08:00",
        endTime: "2026-04-02T10:00:00+08:00",
        generatedAt: "2026-04-02T10:00:01+08:00",
        initialCash: 100000,
        costModel: "ashare_paper_cost_model",
        slippageBps: 5,
        feeModel: "ashare_paper_cost_model",
        slippageModel: "bar_close_bps",
        parameterSnapshot: {
          rule_template: "moving_average_band_v1",
        },
        dataFingerprint: "bars:600036.SH:1d",
        manifestFingerprint: "manifest:rule-run-001",
      },
      performance: {
        barCount: 1250,
        signalCount: 2,
        orderCount: 2,
        tradeCount: 2,
        fillCount: 2,
        winningTradeCount: 1,
        losingTradeCount: 0,
        startingCash: 100000,
        endingCash: 99800,
        endingMarketValue: 520,
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
      notes: [],
    });
    mockedUseRuleResearchData.mockReturnValue({
      snapshot: null,
      error: null,
      fetchedAt: null,
      isLoading: false,
      isRefreshing: false,
      lastRequest: null,
      run: runMock,
      refresh: vi.fn(),
      reset: vi.fn(),
    });

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /研究/ }));

    await waitFor(() => {
      expect(window.location.hash).toBe("#research");
    });

    fireEvent.click(screen.getByRole("button", { name: "5 年" }));
    fireEvent.click(screen.getByRole("button", { name: "快速填充示例并运行" }));

    await waitFor(() => {
      expect(runMock).toHaveBeenCalledWith({
        symbol: "600036.SH",
        timeframe: "1d",
        limit: 1250,
        initialCash: 100000,
        slippageBps: 5,
        ruleTemplate: "moving_average_band_v1",
        ruleConfig: {
          maWindow: 60,
          buyBelowMaPct: 0.05,
          sellAboveMaPct: 0.1,
          targetPosition: 400,
        },
      });
    });
  });

  it("runs rule research with the default form values directly", async () => {
    const runMock = vi.fn().mockResolvedValue(null);
    mockedUseRuleResearchData.mockReturnValue({
      snapshot: null,
      error: null,
      fetchedAt: null,
      isLoading: false,
      isRefreshing: false,
      lastRequest: null,
      run: runMock,
      refresh: vi.fn(),
      reset: vi.fn(),
    });

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /研究/ }));

    await waitFor(() => {
      expect(window.location.hash).toBe("#research");
    });

    const initialCashInput = screen.getByDisplayValue("100000") as HTMLInputElement;
    expect(initialCashInput).toHaveValue(100000);
    expect(initialCashInput).toHaveAttribute("step", "1");

    fireEvent.click(screen.getByRole("button", { name: "运行规则回测" }));

    await waitFor(() => {
      expect(runMock).toHaveBeenCalledWith({
        symbol: "600036.SH",
        timeframe: "1d",
        limit: 750,
        initialCash: 100000,
        slippageBps: 5,
        ruleTemplate: "moving_average_band_v1",
        ruleConfig: {
          maWindow: 60,
          buyBelowMaPct: 0.05,
          sellAboveMaPct: 0.1,
          targetPosition: 400,
        },
      });
    });
  });

  it("shows a standardized baseline-vs-ai comparison when both snapshots exist", async () => {
    mockedUseAiResearchData.mockReturnValue({
      snapshot: {
        datasetName: "cn_equity / 000001.SZ / 15m",
        sourceLabel: "由 research API 生成的 AI 回测结果",
        sourceMode: "live",
        mode: "preview",
        summary: {
          mode: "preview",
          modeLabel: "快速预览",
          resultHeadline: "净收益 120.00，最大回撤 0.0200% ，交易 2 次。",
          sampleMessage: "预览样本说明",
          comparisonMessage: "ai_candidate 相比 baseline 的净收益变化 21.00。",
        },
        klineBars: [],
        equityCurve: [
          {
            time: "2026-04-02T10:00:00+08:00",
            value: 100120,
            baseline: 100000,
          },
        ],
        manifest: {
          runId: "run-ai-001",
          accountId: "paper_account_001",
          strategyId: "ai_bar_judge_v1",
          strategyVersion: "ai_bar_judge_v1",
          handlerName: "AiBarJudgeStrategy",
          description: "LLM-ready bar judgment strategy with a safe heuristic fallback.",
          mode: "preview",
          samplePurpose: "preview",
          symbol: "000001.SZ",
          symbols: ["000001.SZ"],
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
            lookback_bars: "12",
            target_position: "400",
            min_confidence: "0.60",
            provider_mode: "heuristic_stub",
            entry_threshold_pct: "0.0008",
            exit_threshold_pct: "-0.0005",
          },
          dataFingerprint: "bars:000001.SZ:15m:ai",
          manifestFingerprint: "manifest:run-ai-001",
        },
        performance: {
          barCount: 1,
          signalCount: 1,
          orderCount: 1,
          tradeCount: 2,
          fillCount: 2,
          winningTradeCount: 1,
          losingTradeCount: 0,
          startingCash: 100000,
          endingCash: 99980,
          endingMarketValue: 140,
          startingEquity: 100000,
          endingEquity: 100120,
          netPnl: 120,
          totalReturnPct: 0.12,
          maxDrawdownPct: 0.02,
          realizedPnl: 20,
          unrealizedPnl: 100,
          turnover: 4000,
          winRatePct: 100,
        },
        decisions: [
          {
            barKey: "000001.SZ:15m:2026-04-02T10:00:00+08:00",
            eventTime: "2026-04-02T10:00:00+08:00",
            symbol: "000001.SZ",
            signalType: "REBALANCE",
            action: "REBALANCE",
            executionAction: "BUY",
            targetPosition: 400,
            reasonSummary: "ai entered",
            skipReason: null,
            fillCount: 1,
            orderPlanSide: "BUY",
          },
        ],
        experiments: null,
        comparison: {
          baselineLabel: "baseline_default",
          candidateLabel: "ai_candidate",
          candidateKind: "ai_strategy",
          sameSample: true,
          sameMetricSemantics: true,
          netPnlDelta: 21,
          totalReturnDeltaPct: 0.021,
          maxDrawdownDeltaPct: 0.02,
          tradeCountDelta: 1,
          turnoverDelta: 50,
          decisionDiffCount: 1,
          decisionDiffs: [
            {
              barKey: "000001.SZ:15m:2026-04-02T10:00:00+08:00",
              eventTime: "2026-04-02T10:00:00+08:00",
              baselineAction: "SKIP",
              candidateAction: "REBALANCE",
              baselineReason: "baseline skipped",
              candidateReason: "ai entered",
            },
          ],
          summaryMessage: "ai_candidate 相比 baseline 有更高净收益。",
        },
        notes: ["ai note"],
      },
      error: null,
      fetchedAt: "2026-04-02T10:00:00+08:00",
      isLoading: false,
      isRefreshing: false,
      lastRequest: null,
      run: vi.fn(),
      refresh: vi.fn(),
      reset: vi.fn(),
    });
    mockedUseResearchData.mockImplementation(() => ({
      snapshot: {
        datasetName: "cn_equity / 000001.SZ / 15m",
        sourceLabel: "由 research API 生成的真实回测结果",
        sourceMode: "live",
        mode: "evaluation",
        summary: {
          mode: "evaluation",
          modeLabel: "评估样本",
          resultHeadline: "净收益 99.00，最大回撤 0.0000% ，交易 1 次。",
          sampleMessage: "评估样本说明",
          comparisonMessage: null,
        },
        klineBars: [],
        equityCurve: [
          {
            time: "2026-04-02T10:00:00+08:00",
            value: 100000,
            baseline: 100000,
          },
        ],
        manifest: {
          runId: "run-001",
          accountId: "paper_account_001",
          strategyId: "baseline_momentum_v1",
          strategyVersion: "baseline_momentum_v1",
          handlerName: "BaselineMomentumStrategy",
          description: "Long-only threshold momentum against previous close.",
          mode: "evaluation",
          samplePurpose: "evaluation",
          symbol: "000001.SZ",
          symbols: ["000001.SZ"],
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
            entry_threshold_pct: "0.0005",
            exit_threshold_pct: "0",
            trend_lookback_bars: "3",
            min_trend_up_bars: "2",
            strong_entry_threshold_pct: "0.0012",
            reduced_target_ratio: "0.5",
            trailing_stop_pct: "0.01",
          },
          dataFingerprint: "bars:000001.SZ:15m",
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
        decisions: [
          {
            barKey: "000001.SZ:15m:2026-04-02T10:00:00+08:00",
            eventTime: "2026-04-02T10:00:00+08:00",
            symbol: "000001.SZ",
            signalType: "SKIP",
            action: "SKIP",
            executionAction: "SKIP",
            targetPosition: null,
            reasonSummary: "baseline skipped",
            skipReason: "warmup",
            fillCount: 0,
            orderPlanSide: null,
          },
        ],
        experiments: null,
        comparison: null,
        notes: ["research API note"],
      },
      error: null,
      fetchedAt: "2026-04-02T10:00:00+08:00",
      isLoading: false,
      isRefreshing: false,
      refresh: vi.fn(),
    }));

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /研究/ }));

    await waitFor(() => {
      expect(window.location.hash).toBe("#research");
    });

    expect(screen.getByText("baseline_default vs ai_candidate")).toBeInTheDocument();
    expect(screen.getByText("关键决策差异")).toBeInTheDocument();
    expect(screen.getByText("Candidate: ai entered")).toBeInTheDocument();
    expect(screen.getByText("Baseline: baseline skipped")).toBeInTheDocument();
  });
});
