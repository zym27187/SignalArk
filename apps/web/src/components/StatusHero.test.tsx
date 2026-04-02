import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusHero } from "./StatusHero";

describe("StatusHero", () => {
  it("renders the localized runtime summary and error state", () => {
    render(
      <StatusHero
        status={{
          trader_run_id: "run-001",
          instance_id: "instance-A",
          account_id: "paper_account_001",
          control_state: "kill_switch",
          strategy_enabled: true,
          kill_switch_active: true,
          protection_mode_active: false,
          ready: false,
          status: "not_ready",
          health_status: "alive",
          lifecycle_status: "running",
          market_data_fresh: false,
          market_state_available: true,
          latest_final_bar_time: "2026-04-02T10:00:00+08:00",
          current_trading_phase: "CONTINUOUS_AUCTION",
          lease_owner_instance_id: "instance-A",
          lease_expires_at: "2026-04-02T10:00:15+08:00",
          last_heartbeat_at: "2026-04-02T10:00:05+08:00",
          fencing_token: 3,
          env: "dev",
          execution_mode: "paper",
        }}
        isLoading={false}
        error="状态查询失败"
      />,
    );

    expect(screen.getByRole("heading", { name: "模拟交易控制面板" })).toBeInTheDocument();
    expect(screen.getByText("熔断模式 · 运行中 · 待命")).toBeInTheDocument();
    expect(screen.getByText("状态流异常：状态查询失败")).toBeInTheDocument();
    expect(screen.getByText("开发")).toBeInTheDocument();
    expect(screen.getByText("模拟盘")).toBeInTheDocument();
  });
});
