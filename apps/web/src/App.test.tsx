import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { useDashboardData } from "./hooks/use-dashboard-data";
import { useMarketData } from "./hooks/use-market-data";
import { useResearchData } from "./hooks/use-research-data";

vi.mock("./hooks/use-dashboard-data", () => ({
  useDashboardData: vi.fn(),
}));

vi.mock("./hooks/use-market-data", () => ({
  useMarketData: vi.fn(),
}));

vi.mock("./hooks/use-research-data", () => ({
  useResearchData: vi.fn(),
}));

const mockedUseDashboardData = vi.mocked(useDashboardData);
const mockedUseMarketData = vi.mocked(useMarketData);
const mockedUseResearchData = vi.mocked(useResearchData);

describe("App", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
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
          handlerName: "BaselineMomentumStrategy",
          description: "research snapshot",
          symbols: ["000001.SZ"],
          timeframe: "15m",
          barCount: 1,
          startTime: "2026-04-02T10:00:00+08:00",
          endTime: "2026-04-02T10:00:00+08:00",
          initialCash: 100000,
          slippageBps: 5,
          feeModel: "ashare_paper_cost_model",
          slippageModel: "bar_close_bps",
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
        notes: ["research API note"],
      },
      error: null,
      fetchedAt: "2026-04-02T10:00:00+08:00",
      isLoading: false,
      isRefreshing: false,
      refresh: vi.fn(),
    }));
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shares the selected symbol across market and research views", async () => {
    render(<App />);

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
    });
    expect(screen.getByText(/paper_account_001 \/ 平安银行 \(000001\.SZ\)/)).toBeInTheDocument();
  });
});
