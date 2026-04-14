import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BacktestDecisionTable } from "./BacktestDecisionTable";

describe("BacktestDecisionTable", () => {
  it("defaults to descending order, supports toggling sort order, and hides empty confidence", () => {
    render(
      <BacktestDecisionTable
        pageSize={1}
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
            audit: {
              providerId: "heuristic_stub",
              modelOrPolicyVersion: "heuristic_stub_v1",
              decision: "hold",
              confidence: "0.7300",
              reasonSummary: "盘整区间太窄，先观望。",
              fallbackUsed: true,
              fallbackReason: "provider timed out",
            },
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
            audit: {
              providerId: "openai_chat_completions",
              modelOrPolicyVersion: "gpt-5.4-mini",
              decision: "rebalance",
              confidence: "0.8300",
              reasonSummary: "突破阈值后调到目标仓位。",
              fallbackUsed: false,
              fallbackReason: null,
            },
            skipReason: null,
            fillCount: 1,
            orderPlanSide: "BUY",
          },
          {
            barKey: "600036.SH:15m:2026-04-10T10:15:00+08:00",
            eventTime: "2026-04-10T10:15:00+08:00",
            symbol: "600036.SH",
            signalType: "EXIT",
            action: "EXIT",
            executionAction: "SELL",
            targetPosition: 0,
            reasonSummary: "跌破阈值后执行止盈离场。",
            audit: {
              providerId: "deterministic_policy",
              modelOrPolicyVersion: "baseline_momentum_v1",
              decision: "exit",
              confidence: null,
              reasonSummary: "跌破阈值后执行止盈离场。",
              fallbackUsed: false,
              fallbackReason: null,
            },
            skipReason: null,
            fillCount: 1,
            orderPlanSide: "SELL",
          },
        ]}
      />,
    );

    expect(screen.getByRole("columnheader", { name: "策略动作" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "买卖原因排序" })).toHaveValue("desc");
    expect(screen.getByText("第 1 / 3 页 · 显示第 1-1 条，共 3 条")).toBeInTheDocument();
    expect(screen.queryByText("盘整区间太窄，先观望。")).not.toBeInTheDocument();
    expect(screen.queryByText("突破阈值后调到目标仓位。")).not.toBeInTheDocument();

    const exitRow = screen.getByText("跌破阈值后执行止盈离场。").closest("tr");
    expect(exitRow).not.toBeNull();
    expect(within(exitRow as HTMLElement).getAllByText("平仓")).toHaveLength(2);
    expect(within(exitRow as HTMLElement).getByText("下单计划：卖出")).toBeInTheDocument();
    expect(within(exitRow as HTMLElement).queryByText("置信度：--")).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole("combobox", { name: "买卖原因排序" }), {
      target: { value: "asc" },
    });

    expect(screen.getByRole("combobox", { name: "买卖原因排序" })).toHaveValue("asc");
    expect(screen.getByText("第 1 / 3 页 · 显示第 1-1 条，共 3 条")).toBeInTheDocument();
    expect(screen.queryByText("突破阈值后调到目标仓位。")).not.toBeInTheDocument();
    expect(screen.queryByText("跌破阈值后执行止盈离场。")).not.toBeInTheDocument();

    const holdRow = screen.getByText("盘整区间太窄，先观望。").closest("tr");
    expect(holdRow).not.toBeNull();
    expect(within(holdRow as HTMLElement).getByText("观望")).toBeInTheDocument();
    expect(within(holdRow as HTMLElement).getByText("来源：Heuristic Stub")).toBeInTheDocument();
    expect(within(holdRow as HTMLElement).getByText("置信度：0.7300")).toBeInTheDocument();
    expect(
      within(holdRow as HTMLElement).getByText("回退原因：provider timed out"),
    ).toBeInTheDocument();
    expect(within(holdRow as HTMLElement).getByText("下单计划：跳过")).toBeInTheDocument();
    expect(
      within(holdRow as HTMLElement).getByText("跳过原因：模型选择观望"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    expect(screen.getByText("第 2 / 3 页 · 显示第 2-2 条，共 3 条")).toBeInTheDocument();
    expect(screen.queryByText("盘整区间太窄，先观望。")).not.toBeInTheDocument();

    const rebalanceRow = screen.getByText("突破阈值后调到目标仓位。").closest("tr");
    expect(rebalanceRow).not.toBeNull();
    expect(within(rebalanceRow as HTMLElement).getAllByText("再平衡")).toHaveLength(2);
    expect(
      within(rebalanceRow as HTMLElement).getByText("来源：OpenAI Chat Completions"),
    ).toBeInTheDocument();
    expect(within(rebalanceRow as HTMLElement).getByText("下单计划：买入")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("spinbutton", { name: "跳到第几页" }), {
      target: { value: "3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "跳转" }));

    expect(screen.getByText("第 3 / 3 页 · 显示第 3-3 条，共 3 条")).toBeInTheDocument();
    expect(screen.queryByText("突破阈值后调到目标仓位。")).not.toBeInTheDocument();

    const ascendingExitRow = screen.getByText("跌破阈值后执行止盈离场。").closest("tr");
    expect(ascendingExitRow).not.toBeNull();
    expect(within(ascendingExitRow as HTMLElement).queryByText("置信度：--")).not.toBeInTheDocument();
  });
});
