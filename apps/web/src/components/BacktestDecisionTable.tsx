import { formatDateTime, formatDecimal, titleCase } from "../lib/format";
import type { BacktestDecisionSnapshot } from "../types/research";

interface BacktestDecisionTableProps {
  decisions: BacktestDecisionSnapshot[];
}

export function BacktestDecisionTable({ decisions }: BacktestDecisionTableProps) {
  return (
    <div className="table-shell">
      <table className="data-table">
        <thead>
          <tr>
            <th>事件时间</th>
            <th>动作</th>
            <th>信号</th>
            <th>目标仓位</th>
            <th>成交次数</th>
            <th>原因</th>
          </tr>
        </thead>
        <tbody>
          {decisions.map((decision) => (
            <tr key={decision.barKey}>
              <td>{formatDateTime(decision.eventTime)}</td>
              <td>{titleCase(decision.action)}</td>
              <td>{decision.signalType ? titleCase(decision.signalType) : "无"}</td>
              <td>
                {decision.targetPosition === null
                  ? "--"
                  : formatDecimal(decision.targetPosition, 0)}
              </td>
              <td>{decision.fillCount}</td>
              <td>
                <div className="decision-reason">
                  <strong>{decision.reasonSummary}</strong>
                  {decision.skipReason ? <span>跳过：{titleCase(decision.skipReason)}</span> : null}
                  {decision.orderPlanSide ? <span>订单：{titleCase(decision.orderPlanSide)}</span> : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
