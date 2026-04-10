import { useEffect, useState } from "react";

import { formatDateTime, formatDecimal, titleCase } from "../lib/format";
import type { BacktestDecisionSnapshot } from "../types/research";

const DEFAULT_PAGE_SIZE = 8;

interface BacktestDecisionTableProps {
  decisions: BacktestDecisionSnapshot[];
  pageSize?: number;
}

export function BacktestDecisionTable({
  decisions,
  pageSize = DEFAULT_PAGE_SIZE,
}: BacktestDecisionTableProps) {
  const normalizedPageSize = Math.max(1, Math.floor(pageSize));
  const pageCount = Math.max(1, Math.ceil(decisions.length / normalizedPageSize));
  const [page, setPage] = useState(0);
  const decisionSignature =
    decisions.length === 0
      ? "empty"
      : `${decisions.length}:${decisions[0]?.barKey ?? ""}:${decisions[decisions.length - 1]?.barKey ?? ""}`;
  const startIndex = page * normalizedPageSize;
  const endIndex = Math.min(startIndex + normalizedPageSize, decisions.length);
  const visibleDecisions = decisions.slice(startIndex, endIndex);

  useEffect(() => {
    setPage(0);
  }, [decisionSignature]);

  return (
    <div className="table-shell">
      <table className="data-table">
        <thead>
          <tr>
            <th>发生时间</th>
            <th>策略动作</th>
            <th>信号</th>
            <th>目标仓位</th>
            <th>成交笔数</th>
            <th>为什么</th>
          </tr>
        </thead>
        <tbody>
          {visibleDecisions.map((decision) => (
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
                  {decision.skipReason ? <span>跳过原因：{titleCase(decision.skipReason)}</span> : null}
                  <span>下单计划：{titleCase(decision.executionAction)}</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {pageCount > 1 ? (
        <div className="decision-pagination">
          <p className="decision-pagination__summary" aria-live="polite">
            {`第 ${page + 1} / ${pageCount} 页 · 显示第 ${startIndex + 1}-${endIndex} 条，共 ${decisions.length} 条`}
          </p>
          <div className="decision-pagination__actions">
            <button
              type="button"
              className="secondary-button"
              onClick={() => setPage((currentPage) => Math.max(0, currentPage - 1))}
              disabled={page === 0}
            >
              上一页
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() =>
                setPage((currentPage) => Math.min(pageCount - 1, currentPage + 1))
              }
              disabled={page === pageCount - 1}
            >
              下一页
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
