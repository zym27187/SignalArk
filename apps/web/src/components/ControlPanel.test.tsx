import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ControlPanel } from "./ControlPanel";

describe("ControlPanel", () => {
  const status = {
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
    last_cancel_all_at: "2026-04-02T10:05:00+08:00",
  };

  it("requires confirmation before dangerous actions are submitted", () => {
    const onAction = vi.fn();

    render(
      <ControlPanel
        status={status}
        pendingAction={null}
        lastActionResult={null}
        onAction={onAction}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /开启熔断开关/ }));

    expect(onAction).not.toHaveBeenCalled();
    expect(screen.getByText("确认开启熔断开关")).toBeInTheDocument();
    expect(
      screen.getByText("开启后，系统会阻止新的开仓，只保留减仓或清仓相关动作。"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /确认执行/ }));

    expect(onAction).toHaveBeenCalledWith("enableKillSwitch");
  });

  it("shows the latest cancel-all result with structured counts", () => {
    render(
      <ControlPanel
        status={status}
        pendingAction={null}
        lastActionResult={{
          actionKey: "cancelAll",
          actionLabel: "全部撤单",
          accepted: true,
          controlState: "kill_switch",
          requestedAt: "2026-04-02T10:06:00+08:00",
          effectiveAt: "2026-04-02T10:06:01+08:00",
          message: "全撤请求已应用到当前活动订单。",
          requestedOrderCount: 5,
          cancelledOrderCount: 3,
          skippedOrderCount: 2,
        }}
        onAction={vi.fn()}
      />,
    );

    const resultPanel = screen.getByText("最近一次动作").closest(".control-panel__result");

    expect(resultPanel).not.toBeNull();
    expect(within(resultPanel as HTMLElement).getByText("全部撤单")).toBeInTheDocument();
    expect(within(resultPanel as HTMLElement).getByText("已落地")).toBeInTheDocument();
    expect(
      within(resultPanel as HTMLElement).getByText("全撤请求已应用到当前活动订单。"),
    ).toBeInTheDocument();
    expect(
      within(resultPanel as HTMLElement).getByText("控制状态：已紧急暂停"),
    ).toBeInTheDocument();
    expect(within(resultPanel as HTMLElement).getByText("请求数")).toBeInTheDocument();
    expect(within(resultPanel as HTMLElement).getByText("成功撤单")).toBeInTheDocument();
    expect(within(resultPanel as HTMLElement).getByText("跳过数")).toBeInTheDocument();
    expect(
      within(resultPanel as HTMLElement).getByText("这意味着系统已经开始撤销当前排队订单，但保护性减仓单可能继续保留。"),
    ).toBeInTheDocument();
    expect(within(resultPanel as HTMLElement).getByText("5")).toBeInTheDocument();
    expect(within(resultPanel as HTMLElement).getByText("3")).toBeInTheDocument();
    expect(within(resultPanel as HTMLElement).getByText("2")).toBeInTheDocument();
  });
});
