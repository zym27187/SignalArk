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
            reasonSummary: "market regime is mixed",
            audit: {
              providerId: "heuristic_stub",
              modelOrPolicyVersion: "heuristic_stub_v1",
              decision: "hold",
              confidence: "0.7300",
              reasonSummary: "market regime is mixed",
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
            reasonSummary: "model confirmed the bullish stack",
            audit: {
              providerId: "openai_chat_completions",
              modelOrPolicyVersion: "gpt-5.4-mini",
              decision: "rebalance",
              confidence: "0.8300",
              reasonSummary: "model confirmed the bullish stack",
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
    expect(screen.queryByText("当前市场方向信号分化，先保持观望。")).not.toBeInTheDocument();
    expect(screen.queryByText("模型确认最近一组 K 线偏多，因此执行买入。")).not.toBeInTheDocument();

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
    expect(screen.queryByText("模型确认最近一组 K 线偏多，因此执行买入。")).not.toBeInTheDocument();
    expect(screen.queryByText("跌破阈值后执行止盈离场。")).not.toBeInTheDocument();

    const holdRow = screen.getByText("当前市场方向信号分化，先保持观望。").closest("tr");
    expect(holdRow).not.toBeNull();
    expect(within(holdRow as HTMLElement).getByText("观望")).toBeInTheDocument();
    expect(within(holdRow as HTMLElement).getByText("来源：Heuristic Stub")).toBeInTheDocument();
    expect(within(holdRow as HTMLElement).getByText("置信度：0.7300")).toBeInTheDocument();
    expect(
      within(holdRow as HTMLElement).getByText("回退原因：模型服务响应超时"),
    ).toBeInTheDocument();
    expect(
      within(holdRow as HTMLElement).getByText("下单计划：跳过（未生成可执行订单）"),
    ).toBeInTheDocument();
    expect(
      within(holdRow as HTMLElement).getByText("跳过原因：模型选择观望"),
    ).toBeInTheDocument();
    expect(
      within(holdRow as HTMLElement).getByText(
        "跳过说明：模型明确给出了观望动作，所以这一步只记录判断，不生成交易信号。",
      ),
    ).toBeInTheDocument();
    expect(within(holdRow as HTMLElement).getByText("原因代码：ai_decision_hold")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    expect(screen.getByText("第 2 / 3 页 · 显示第 2-2 条，共 3 条")).toBeInTheDocument();
    expect(screen.queryByText("当前市场方向信号分化，先保持观望。")).not.toBeInTheDocument();

    const rebalanceRow = screen.getByText("模型确认最近一组 K 线偏多，因此执行买入。").closest("tr");
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
    expect(screen.queryByText("模型确认最近一组 K 线偏多，因此执行买入。")).not.toBeInTheDocument();

    const ascendingExitRow = screen.getByText("跌破阈值后执行止盈离场。").closest("tr");
    expect(ascendingExitRow).not.toBeNull();
    expect(within(ascendingExitRow as HTMLElement).queryByText("置信度：--")).not.toBeInTheDocument();
  });

  it("localizes moving-average rule reasons and skip explanations", () => {
    render(
      <BacktestDecisionTable
        decisions={[
          {
            barKey: "600036.SH:1d:2026-04-10T14:00:00+08:00",
            eventTime: "2026-04-10T14:00:00+08:00",
            symbol: "600036.SH",
            signalType: "ENTRY",
            action: "ENTRY",
            executionAction: "BUY",
            targetPosition: 400,
            reasonSummary:
              "close 80 fell to buy threshold 88.6667 around ma3 93.3333; deviation_pct -14.2857 <= -buyBelowMaPct 5.0000; target_position 400",
            audit: {
              providerId: "deterministic_policy",
              modelOrPolicyVersion: "moving_average_band_v1",
              decision: "entry",
              confidence: null,
              reasonSummary:
                "close 80 fell to buy threshold 88.6667 around ma3 93.3333; deviation_pct -14.2857 <= -buyBelowMaPct 5.0000; target_position 400",
              fallbackUsed: false,
              fallbackReason: null,
            },
            skipReason: null,
            fillCount: 1,
            orderPlanSide: "BUY",
          },
          {
            barKey: "600036.SH:1d:2026-04-11T14:00:00+08:00",
            eventTime: "2026-04-11T14:00:00+08:00",
            symbol: "600036.SH",
            signalType: null,
            action: "HOLD",
            executionAction: "SKIP",
            targetPosition: null,
            reasonSummary:
              "close 100 stayed above buy_trigger 95.0000 around ma3 100.0000; keep waiting",
            audit: {
              providerId: "deterministic_policy",
              modelOrPolicyVersion: "moving_average_band_v1",
              decision: "hold",
              confidence: null,
              reasonSummary:
                "close 100 stayed above buy_trigger 95.0000 around ma3 100.0000; keep waiting",
              fallbackUsed: false,
              fallbackReason: null,
            },
            skipReason: "moving_average_band_buy_threshold_not_met",
            fillCount: 0,
            orderPlanSide: null,
          },
        ]}
      />,
    );

    expect(
      screen.getByText(/收盘价 80 已跌到买入阈值 88\.6667/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("下单计划：买入"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "跳过说明：当前收盘价还没有跌到买入阈值，因此这一步继续空仓等待。",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("原因代码：moving_average_band_buy_threshold_not_met"),
    ).toBeInTheDocument();
  });
});
