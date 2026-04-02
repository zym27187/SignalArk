import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { useDashboardData } from "./hooks/use-dashboard-data";
import { useMarketData } from "./hooks/use-market-data";

vi.mock("./hooks/use-dashboard-data", () => ({
  useDashboardData: vi.fn(),
}));

vi.mock("./hooks/use-market-data", () => ({
  useMarketData: vi.fn(),
}));

const mockedUseDashboardData = vi.mocked(useDashboardData);
const mockedUseMarketData = vi.mocked(useMarketData);

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
        },
        positions: [],
        orders: [],
        events: [],
        sectionErrors: {},
        fetchedAt: "2026-04-02T10:00:00+08:00",
      },
      isLoading: false,
      isRefreshing: false,
      pendingAction: null,
      actionMessage: null,
      refresh: vi.fn(),
      performAction: vi.fn(),
    });
    mockedUseMarketData.mockImplementation(() => ({
      snapshot: {
        symbol: null,
        timeframe: null,
        bars: [],
        equityCurve: [],
        sectionErrors: {},
        fetchedAt: null,
      },
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

    fireEvent.click(screen.getByRole("tab", { name: "000001.SZ" }));

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
    expect(screen.getByText(/paper_account_001 \/ 000001\.SZ/)).toBeInTheDocument();
  });
});
