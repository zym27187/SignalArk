import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BalanceSummaryPanel } from "./BalanceSummaryPanel";

describe("BalanceSummaryPanel", () => {
  it("explains how cash and positions form account equity", () => {
    render(
      <BalanceSummaryPanel
        summary={{
          account_id: "paper_account_001",
          cash_balance: "98000",
          available_cash: "97500",
          frozen_cash: "500",
          market_value: "11850",
          equity: "109850",
          unrealized_pnl: "90",
          realized_pnl: "0",
          position_count: 1,
          cash_as_of_time: "2026-04-02T10:03:00+08:00",
          positions_as_of_time: "2026-04-02T10:00:00+08:00",
          as_of_time: "2026-04-02T10:03:00+08:00",
          summary_message: "账户权益由现金余额和持仓市值共同组成。",
          cash_explanation:
            "现金余额 = 可用资金 + 冻结资金。可用资金还能继续下单，冻结资金通常表示仍有订单占用资金。",
          position_explanation: "持仓市值按当前持仓数量乘以最新标记价格估算。",
          equity_explanation:
            "账户权益 = 现金余额 + 持仓市值。未实现盈亏来自持仓价格波动，已实现盈亏来自已经完成的买卖结果。",
        }}
      />,
    );

    expect(screen.getByText("账户权益由现金余额和持仓市值共同组成。")).toBeInTheDocument();
    expect(screen.getAllByText("109,850.00")).toHaveLength(2);
    expect(screen.getByText("现金变化")).toBeInTheDocument();
    expect(screen.getByText("持仓变化")).toBeInTheDocument();
    expect(screen.getByText("权益变化")).toBeInTheDocument();
  });
});
