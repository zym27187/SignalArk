import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BacktestDecisionTable } from "./BacktestDecisionTable";

describe("BacktestDecisionTable", () => {
  it("renders strategy actions separately from execution plans", () => {
    render(
      <BacktestDecisionTable
        decisions={[
          {
            barKey: "600036.SH:15m:2026-04-10T09:45:00+08:00",
            eventTime: "2026-04-10T09:45:00+08:00",
            symbol: "600036.SH",
            signalType: null,
            action: "HOLD",
            executionAction: "SKIP",
            targetPosition: null,
            reasonSummary: "盘整区间太窄，先观望。",
            skipReason: "ai_decision_hold",
            fillCount: 0,
            orderPlanSide: null,
          },
          {
            barKey: "600036.SH:15m:2026-04-10T10:00:00+08:00",
            eventTime: "2026-04-10T10:00:00+08:00",
            symbol: "600036.SH",
            signalType: "REBALANCE",
            action: "REBALANCE",
            executionAction: "BUY",
            targetPosition: 400,
            reasonSummary: "突破阈值后调到目标仓位。",
            skipReason: null,
            fillCount: 1,
            orderPlanSide: "BUY",
          },
        ]}
      />,
    );

    expect(screen.getByRole("columnheader", { name: "策略动作" })).toBeInTheDocument();

    const holdRow = screen.getByText("盘整区间太窄，先观望。").closest("tr");
    expect(holdRow).not.toBeNull();
    expect(within(holdRow as HTMLElement).getByText("观望")).toBeInTheDocument();
    expect(within(holdRow as HTMLElement).getByText("下单计划：跳过")).toBeInTheDocument();
    expect(
      within(holdRow as HTMLElement).getByText("跳过原因：模型选择观望"),
    ).toBeInTheDocument();

    const rebalanceRow = screen.getByText("突破阈值后调到目标仓位。").closest("tr");
    expect(rebalanceRow).not.toBeNull();
    expect(within(rebalanceRow as HTMLElement).getAllByText("再平衡")).toHaveLength(2);
    expect(within(rebalanceRow as HTMLElement).getByText("下单计划：买入")).toBeInTheDocument();
  });
});
