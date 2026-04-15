import { formatDateTime, formatDecimal, formatSignedMoney } from "../lib/format";
import type { BalanceSummaryPayload } from "../types/api";

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

  const primaryMetrics = [
    {
      label: "现金余额",
      value: formatDecimal(summary.cash_balance, 2),
      hint: "账户当前现金总额",
    },
    {
      label: "可用资金",
      value: formatDecimal(summary.available_cash, 2),
      hint: "当前可继续用于下单的资金",
    },
    {
      label: "冻结资金",
      value: formatDecimal(summary.frozen_cash, 2),
      hint: "被未完成订单暂时占用",
    },
    {
      label: "账户权益",
      value: formatDecimal(summary.equity, 2),
      hint: "现金与持仓市值合计",
    },
  ];
  const secondaryMetrics = [
    {
      label: "持仓市值",
      value: formatDecimal(summary.market_value, 2),
      hint: "按最新标记价估值",
    },
    {
      label: "可估值持仓",
      value: `${summary.position_count} 个`,
      hint: "当前参与估值的持仓数量",
    },
    {
      label: "未实现盈亏",
      value: formatSignedMoney(summary.unrealized_pnl),
      hint: "来自持仓价格波动",
    },
    {
      label: "已实现盈亏",
      value: formatSignedMoney(summary.realized_pnl),
      hint: "来自已完成卖出结果",
    },
  ];

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

      <div className="balance-summary__metrics">
        {primaryMetrics.map((metric) => (
          <article
            key={metric.label}
            className="balance-summary__metric"
          >
            <p className="mini-label">{metric.label}</p>
            <strong>{metric.value}</strong>
            <p>{metric.hint}</p>
          </article>
        ))}
      </div>

      <div className="balance-summary__metrics balance-summary__metrics--secondary">
        {secondaryMetrics.map((metric) => (
          <article
            key={metric.label}
            className="balance-summary__metric balance-summary__metric--secondary"
          >
            <p className="mini-label">{metric.label}</p>
            <strong>{metric.value}</strong>
            <p>{metric.hint}</p>
          </article>
        ))}
      </div>

      <details className="balance-summary__details">
        <summary className="balance-summary__details-summary">查看计算口径</summary>
        <div className="balance-summary__details-grid">
          <article className="balance-summary__detail">
            <p className="mini-label">现金口径</p>
            <p>{summary.cash_explanation}</p>
          </article>
          <article className="balance-summary__detail">
            <p className="mini-label">持仓口径</p>
            <p>{summary.position_explanation}</p>
          </article>
          <article className="balance-summary__detail">
            <p className="mini-label">权益口径</p>
            <p>{summary.equity_explanation}</p>
          </article>
        </div>
      </details>
    </div>
  );
}
