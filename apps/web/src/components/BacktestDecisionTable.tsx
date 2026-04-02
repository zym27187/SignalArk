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
            <th>Event Time</th>
            <th>Action</th>
            <th>Signal</th>
            <th>Target Position</th>
            <th>Fill Count</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {decisions.map((decision) => (
            <tr key={decision.barKey}>
              <td>{formatDateTime(decision.eventTime)}</td>
              <td>{decision.action}</td>
              <td>{decision.signalType ? titleCase(decision.signalType) : "None"}</td>
              <td>
                {decision.targetPosition === null
                  ? "--"
                  : formatDecimal(decision.targetPosition, 0)}
              </td>
              <td>{decision.fillCount}</td>
              <td>
                <div className="decision-reason">
                  <strong>{decision.reasonSummary}</strong>
                  {decision.skipReason ? <span>Skip: {decision.skipReason}</span> : null}
                  {decision.orderPlanSide ? <span>Order: {decision.orderPlanSide}</span> : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

