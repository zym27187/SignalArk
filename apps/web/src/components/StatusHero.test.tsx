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
          last_strategy_id: "ai_bar_judge_v1",
          last_strategy_decision_at: "2026-04-02T09:58:00+08:00",
          last_strategy_audit: {
            provider_id: "heuristic_stub",
            model_or_policy_version: "heuristic_stub_v1",
            decision: "hold",
            confidence: "0.7100",
            reason_summary: "当前波段方向还不够清晰，先维持观望。",
            fallback_used: true,
            fallback_reason: "provider timeout",
          },
          lease_owner_instance_id: "instance-A",
          lease_expires_at: "2026-04-02T10:00:15+08:00",
          last_heartbeat_at: "2026-04-02T10:00:05+08:00",
          fencing_token: 3,
          env: "dev",
          execution_mode: "paper",
          degraded_mode: {
            status: "degraded",
            reason_code: "MARKET_DATA_STALE",
            message: "当前行情存在但已经不新鲜，系统读取到的盘中状态可能落后于真实市场。",
            data_source: "eastmoney",
            effective_at: "2026-04-02T10:00:00+08:00",
            impact: "你仍然可以查看历史轨迹，但不能把当前价格、权益变化和自动判断当成最新盘中事实。",
            suggested_action: "优先查看 runtime bar audit 的最后时间，并确认 collector 是否持续产出 closed bar。",
          },
        }}
        isLoading={false}
        error="状态查询失败"
      />,
    );

    expect(screen.getByRole("heading", { name: "交易运行总览" })).toBeInTheDocument();
    expect(
      screen.getByText("系统当前存在明确的诊断降级，下面会直接说明原因、影响和建议动作。"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("当前行情存在但已经不新鲜，系统读取到的盘中状态可能落后于真实市场。"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("当前影响：你仍然可以查看历史轨迹，但不能把当前价格、权益变化和自动判断当成最新盘中事实。"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("建议动作：优先查看 runtime bar audit 的最后时间，并确认 collector 是否持续产出 closed bar。"),
    ).toBeInTheDocument();
    expect(screen.getByText("状态读取失败：状态查询失败")).toBeInTheDocument();
    expect(screen.getByText("开发环境")).toBeInTheDocument();
    expect(screen.getByText("模拟交易")).toBeInTheDocument();
    expect(screen.getByText("最近一次策略判断")).toBeInTheDocument();
    expect(screen.getByText("当前波段方向还不够清晰，先维持观望。")).toBeInTheDocument();
    expect(screen.getByText("置信度：0.7100")).toBeInTheDocument();
    expect(screen.getByText("已降级到 deterministic fallback：provider timeout")).toBeInTheDocument();
  });
});
