import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusHero } from "./StatusHero";

describe("StatusHero", () => {
  it("renders the simplified runtime summary and error state", () => {
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

    expect(screen.getByRole("heading", { name: "交易运行总览" })).toBeInTheDocument();
    expect(
      screen.getByText("当前已紧急暂停，系统运行中，暂时等待中。自动策略已开启。"),
    ).toBeInTheDocument();
    expect(screen.getByText("状态读取失败：状态查询失败")).toBeInTheDocument();
    expect(screen.getByText("开发环境")).toBeInTheDocument();
    expect(screen.getByText("模拟交易")).toBeInTheDocument();
  });
});
