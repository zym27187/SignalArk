import { formatDateTime, formatDecimal, formatSignedMoney } from "../lib/format";
import type { BalanceSummaryPayload } from "../types/api";
import { DefinitionGrid } from "./DefinitionGrid";

interface BalanceSummaryPanelProps {
  summary: BalanceSummaryPayload | null;
  error?: string;
}

export function BalanceSummaryPanel({ summary, error }: BalanceSummaryPanelProps) {
  if (error && !summary) {
    return (
      <div className="balance-summary balance-summary--empty">
        <p className="empty-state__title">资金状态暂时不可用</p>
        <p className="empty-state__copy">当前无法确认现金、冻结资金和权益之间的关系：{error}</p>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="balance-summary balance-summary--empty">
        <p className="empty-state__title">还没有资金快照</p>
        <p className="empty-state__copy">
          等账户余额和持仓快照写入后，这里会解释现金余额、冻结资金和账户权益之间的关系。
        </p>
      </div>
    );
  }

  return (
    <div className="balance-summary">
      <div className="balance-summary__hero">
        <div>
          <p className="mini-label">账户结论</p>
          <strong>{summary.summary_message}</strong>
        </div>
        <div className="balance-summary__meta">
          <span>关键快照：{formatDateTime(summary.as_of_time)}</span>
          <span>现金快照：{formatDateTime(summary.cash_as_of_time)}</span>
          <span>持仓快照：{formatDateTime(summary.positions_as_of_time)}</span>
        </div>
      </div>

      {error ? <p className="balance-summary__error">部分字段刷新失败：{error}</p> : null}

      <DefinitionGrid
        items={[
          {
            label: "现金余额",
            value: formatDecimal(summary.cash_balance, 2),
            hint: "账户当前的现金总额，已经包含可用资金和冻结资金。",
          },
          {
            label: "可用资金",
            value: formatDecimal(summary.available_cash, 2),
            hint: "这部分资金还能继续用于新的买入或其他需要占用资金的动作。",
          },
          {
            label: "冻结资金",
            value: formatDecimal(summary.frozen_cash, 2),
            hint: "通常表示仍有未完成订单占用了这部分现金，因此它暂时不能再被重复使用。",
          },
          {
            label: "持仓市值",
            value: formatDecimal(summary.market_value, 2),
            hint: `当前共有 ${summary.position_count} 个持仓在估值中。`,
          },
          {
            label: "账户权益",
            value: formatDecimal(summary.equity, 2),
            hint: "账户权益会把现金余额和持仓市值一起算进去。",
          },
          {
            label: "未实现盈亏",
            value: formatSignedMoney(summary.unrealized_pnl),
            hint: "表示持仓如果按当前价格估值，相对成本价的浮动结果。",
          },
          {
            label: "已实现盈亏",
            value: formatSignedMoney(summary.realized_pnl),
            hint: "表示已经完成卖出并真正落袋的盈亏结果。",
          },
        ]}
      />

      <div className="balance-summary__explanations">
        <article className="balance-summary__explanation">
          <p className="mini-label">现金变化</p>
          <strong>{formatDecimal(summary.cash_balance, 2)}</strong>
          <p>{summary.cash_explanation}</p>
        </article>
        <article className="balance-summary__explanation">
          <p className="mini-label">持仓变化</p>
          <strong>{formatDecimal(summary.market_value, 2)}</strong>
          <p>{summary.position_explanation}</p>
        </article>
        <article className="balance-summary__explanation">
          <p className="mini-label">权益变化</p>
          <strong>{formatDecimal(summary.equity, 2)}</strong>
          <p>{summary.equity_explanation}</p>
        </article>
      </div>
    </div>
  );
}
