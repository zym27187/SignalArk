import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDashboardData } from "./use-dashboard-data";
import {
  fetchActiveOrders,
  fetchFillHistory,
  fetchOrderHistory,
  fetchPositions,
  fetchReplayEvents,
  fetchStatus,
  postControlAction,
} from "../lib/api";

vi.mock("../lib/api", () => ({
  fetchStatus: vi.fn(),
  fetchPositions: vi.fn(),
  fetchActiveOrders: vi.fn(),
  fetchOrderHistory: vi.fn(),
  fetchFillHistory: vi.fn(),
  fetchReplayEvents: vi.fn(),
  postControlAction: vi.fn(),
}));

const mockedFetchStatus = vi.mocked(fetchStatus);
const mockedFetchPositions = vi.mocked(fetchPositions);
const mockedFetchActiveOrders = vi.mocked(fetchActiveOrders);
const mockedFetchOrderHistory = vi.mocked(fetchOrderHistory);
const mockedFetchFillHistory = vi.mocked(fetchFillHistory);
const mockedFetchReplayEvents = vi.mocked(fetchReplayEvents);
const mockedPostControlAction = vi.mocked(postControlAction);

describe("useDashboardData", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  it("preserves previous section data when a refresh only partially succeeds", async () => {
    mockedFetchStatus
      .mockResolvedValueOnce({
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
      })
      .mockRejectedValueOnce(new Error("status feed unavailable"));
    mockedFetchPositions
      .mockResolvedValueOnce({
        account_id: "paper_account_001",
        positions: [
          {
            account_id: "paper_account_001",
            exchange: "cn_equity",
            symbol: "600036.SH",
            qty: "300",
            sellable_qty: "300",
            avg_entry_price: "39.20",
            mark_price: "39.50",
            unrealized_pnl: "90",
            realized_pnl: "0",
            status: "OPEN",
            updated_at: "2026-04-02T10:00:00+08:00",
          },
        ],
      })
      .mockRejectedValueOnce(new Error("positions feed unavailable"));
    mockedFetchActiveOrders
      .mockResolvedValueOnce({
        account_id: "paper_account_001",
        orders: [],
      })
      .mockResolvedValueOnce({
        account_id: "paper_account_001",
        orders: [
          {
            order_id: "order-001",
            order_intent_id: "intent-001",
            symbol: "600036.SH",
            side: "BUY",
            order_type: "MARKET",
            qty: "100",
            filled_qty: "0",
            status: "NEW",
            reduce_only: false,
            submitted_at: "2026-04-02T10:01:00+08:00",
            updated_at: "2026-04-02T10:01:00+08:00",
          },
        ],
      });
    mockedFetchOrderHistory
      .mockResolvedValueOnce({
        filters: {},
        count: 0,
        orders: [],
      })
      .mockResolvedValueOnce({
        filters: {},
        count: 1,
        orders: [
          {
            order_id: "order-001",
            order_intent_id: "intent-001",
            signal_id: "signal-001",
            trader_run_id: "run-001",
            account_id: "paper_account_001",
            exchange_order_id: "paper-order-001",
            symbol: "600036.SH",
            side: "BUY",
            order_type: "MARKET",
            time_in_force: "DAY",
            qty: "100",
            price: null,
            filled_qty: "100",
            avg_fill_price: "39.50",
            status: "FILLED",
            reduce_only: false,
            risk_decision: "ALLOW",
            risk_reason: null,
            submitted_at: "2026-04-02T10:01:00+08:00",
            updated_at: "2026-04-02T10:02:00+08:00",
            last_error_code: null,
            last_error_message: null,
          },
        ],
      });
    mockedFetchFillHistory
      .mockResolvedValueOnce({
        filters: {},
        count: 1,
        fills: [
          {
            fill_id: "fill-001",
            order_id: "order-001",
            order_intent_id: "intent-001",
            trader_run_id: "run-001",
            account_id: "paper_account_001",
            exchange_fill_id: "paper-fill-001",
            symbol: "600036.SH",
            side: "BUY",
            qty: "100",
            price: "39.50",
            fee: "1.00",
            fee_asset: "CNY",
            liquidity_type: "TAKER",
            fill_time: "2026-04-02T10:02:00+08:00",
            created_at: "2026-04-02T10:02:00+08:00",
            reduce_only: false,
          },
        ],
      })
      .mockRejectedValueOnce(new Error("fills feed unavailable"));
    mockedFetchReplayEvents
      .mockResolvedValueOnce({
        filters: {},
        count: 1,
        events: [
          {
            event_id: "event-001",
            event_type: "runtime.ready",
            source: "trader",
            trader_run_id: "run-001",
            account_id: "paper_account_001",
            exchange: "cn_equity",
            symbol: "600036.SH",
            related_object_type: "runtime",
            event_time: "2026-04-02T10:00:00+08:00",
            ingest_time: "2026-04-02T10:00:00+08:00",
            created_at: "2026-04-02T10:00:00+08:00",
            payload_json: { ready: true },
          },
        ],
      })
      .mockRejectedValueOnce(new Error("events feed unavailable"));

    const { result } = renderHook(() => useDashboardData());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.snapshot.status?.trader_run_id).toBe("run-001");
    expect(result.current.snapshot.positions).toHaveLength(1);
    expect(result.current.snapshot.orders).toHaveLength(0);
    expect(result.current.snapshot.orderHistory).toHaveLength(0);
    expect(result.current.snapshot.fills).toHaveLength(1);
    expect(result.current.snapshot.events).toHaveLength(1);

    await act(async () => {
      await result.current.refresh();
    });

    await waitFor(() => {
      expect(result.current.isRefreshing).toBe(false);
    });

    expect(result.current.snapshot.status?.trader_run_id).toBe("run-001");
    expect(result.current.snapshot.positions).toHaveLength(1);
    expect(result.current.snapshot.orders).toHaveLength(1);
    expect(result.current.snapshot.orderHistory).toHaveLength(1);
    expect(result.current.snapshot.fills).toHaveLength(1);
    expect(result.current.snapshot.events).toHaveLength(1);
    expect(result.current.snapshot.sectionErrors.status).toBe("status feed unavailable");
    expect(result.current.snapshot.sectionErrors.positions).toBe("positions feed unavailable");
    expect(result.current.snapshot.sectionErrors.fillHistory).toBe("fills feed unavailable");
    expect(result.current.snapshot.sectionErrors.events).toBe("events feed unavailable");
  });

  it("localizes control-action responses and refreshes the dashboard", async () => {
    mockedFetchStatus.mockResolvedValue({
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
    });
    mockedFetchPositions.mockResolvedValue({
      account_id: "paper_account_001",
      positions: [],
    });
    mockedFetchActiveOrders.mockResolvedValue({
      account_id: "paper_account_001",
      orders: [],
    });
    mockedFetchOrderHistory.mockResolvedValue({
      filters: {},
      count: 0,
      orders: [],
    });
    mockedFetchFillHistory.mockResolvedValue({
      filters: {},
      count: 0,
      fills: [],
    });
    mockedFetchReplayEvents.mockResolvedValue({
      filters: {},
      count: 0,
      events: [],
    });
    mockedPostControlAction.mockResolvedValue({
      accepted: true,
      control_state: "strategy_paused",
      trader_run_id: "run-001",
      instance_id: "instance-A",
      effective_at: "2026-04-02T10:02:00+08:00",
      message: "Strategy paused.",
    });

    const { result } = renderHook(() => useDashboardData());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    await act(async () => {
      await result.current.performAction("pauseStrategy");
    });

    expect(mockedPostControlAction).toHaveBeenCalledWith("pauseStrategy");
    expect(result.current.actionMessage).toBe("策略已暂停。");
    expect(mockedFetchStatus).toHaveBeenCalledTimes(2);
  });

  it("applies shared activity filters to history and replay requests", async () => {
    mockedFetchStatus.mockResolvedValue({
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
    });
    mockedFetchPositions.mockResolvedValue({
      account_id: "paper_account_001",
      positions: [],
    });
    mockedFetchActiveOrders.mockResolvedValue({
      account_id: "paper_account_001",
      orders: [],
    });
    mockedFetchOrderHistory.mockResolvedValue({
      filters: {},
      count: 0,
      orders: [],
    });
    mockedFetchFillHistory.mockResolvedValue({
      filters: {},
      count: 0,
      fills: [],
    });
    mockedFetchReplayEvents.mockResolvedValue({
      filters: {},
      count: 0,
      events: [],
    });

    const { result } = renderHook(() => useDashboardData());

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    await act(async () => {
      await result.current.applyActivityFilters({
        symbol: "600036.SH",
        status: "filled",
        orderId: "22222222-2222-4222-8222-222222222222",
        traderRunId: "11111111-1111-4111-8111-111111111111",
        startTime: "2026-04-02T10:00",
        endTime: "2026-04-02T11:00",
        limit: 25,
      });
    });

    expect(mockedFetchOrderHistory).toHaveBeenLastCalledWith({
      symbol: "600036.SH",
      status: "FILLED",
      traderRunId: "11111111-1111-4111-8111-111111111111",
      startTime: new Date("2026-04-02T10:00").toISOString(),
      endTime: new Date("2026-04-02T11:00").toISOString(),
      limit: 25,
    });
    expect(mockedFetchFillHistory).toHaveBeenLastCalledWith({
      symbol: "600036.SH",
      orderId: "22222222-2222-4222-8222-222222222222",
      traderRunId: "11111111-1111-4111-8111-111111111111",
      startTime: new Date("2026-04-02T10:00").toISOString(),
      endTime: new Date("2026-04-02T11:00").toISOString(),
      limit: 25,
    });
    expect(mockedFetchReplayEvents).toHaveBeenLastCalledWith({
      symbol: "600036.SH",
      traderRunId: "11111111-1111-4111-8111-111111111111",
      startTime: new Date("2026-04-02T10:00").toISOString(),
      endTime: new Date("2026-04-02T11:00").toISOString(),
      limit: 25,
    });
  });
});
