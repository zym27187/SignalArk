import { useEffect, useState } from "react";

import { formatDateTime, formatDecimal, titleCase } from "../lib/format";
import {
  describeResearchSkipReason,
  localizeResearchReason,
} from "../lib/research-copy";
import type { BacktestDecisionSnapshot } from "../types/research";

const DEFAULT_PAGE_SIZE = 8;
type DecisionSortOrder = "desc" | "asc";

function formatAuditProvider(providerId: string | null | undefined): string {
  switch (providerId) {
    case "openai_chat_completions":
      return "OpenAI Chat Completions";
    case "heuristic_stub":
      return "Heuristic Stub";
    case "deterministic_policy":
      return "Deterministic Policy";
    default:
      return providerId ? titleCase(providerId) : "--";
  }
}

function parseDecisionTime(eventTime: string): number {
  const parsedTime = Date.parse(eventTime);
  return Number.isNaN(parsedTime) ? 0 : parsedTime;
}

function compareDecisions(
  left: BacktestDecisionSnapshot,
  right: BacktestDecisionSnapshot,
  sortOrder: DecisionSortOrder,
): number {
  const timestampDelta = parseDecisionTime(left.eventTime) - parseDecisionTime(right.eventTime);
  if (timestampDelta !== 0) {
    return sortOrder === "asc" ? timestampDelta : -timestampDelta;
  }

  const barKeyDelta = left.barKey.localeCompare(right.barKey);
  return sortOrder === "asc" ? barKeyDelta : -barKeyDelta;
}

interface BacktestDecisionTableProps {
  decisions: BacktestDecisionSnapshot[];
  pageSize?: number;
}

export function BacktestDecisionTable({
  decisions,
  pageSize = DEFAULT_PAGE_SIZE,
}: BacktestDecisionTableProps) {
  const normalizedPageSize = Math.max(1, Math.floor(pageSize));
  const [sortOrder, setSortOrder] = useState<DecisionSortOrder>("desc");
  const sortedDecisions = [...decisions].sort((left, right) =>
    compareDecisions(left, right, sortOrder),
  );
  const pageCount = Math.max(1, Math.ceil(sortedDecisions.length / normalizedPageSize));
  const [page, setPage] = useState(0);
  const [pageInput, setPageInput] = useState("1");
  const decisionSignature =
    sortedDecisions.length === 0
      ? "empty"
      : `${sortedDecisions.length}:${sortedDecisions[0]?.barKey ?? ""}:${sortedDecisions[sortedDecisions.length - 1]?.barKey ?? ""}`;
  const startIndex = page * normalizedPageSize;
  const endIndex = Math.min(startIndex + normalizedPageSize, sortedDecisions.length);
  const visibleDecisions = sortedDecisions.slice(startIndex, endIndex);

  useEffect(() => {
    setPage(0);
  }, [decisionSignature, sortOrder]);

  useEffect(() => {
    setPageInput(String(page + 1));
  }, [page]);

  function jumpToPage() {
    const nextPage = Number.parseInt(pageInput, 10);

    if (!Number.isFinite(nextPage)) {
      setPageInput(String(page + 1));
      return;
    }

    const normalizedPage = Math.min(pageCount, Math.max(1, nextPage));
    setPage(normalizedPage - 1);
    setPageInput(String(normalizedPage));
  }

  return (
    <div className="table-shell">
      <div className="decision-table__toolbar">
        <p className="decision-table__summary">{`当前按时间${sortOrder === "desc" ? "倒序" : "正序"}展示`}</p>
        <label className="decision-table__sort">
          排序
          <select
            aria-label="买卖原因排序"
            className="decision-table__sort-select"
            value={sortOrder}
            onChange={(event) => setSortOrder(event.target.value as DecisionSortOrder)}
          >
            <option value="desc">倒序（最新在前）</option>
            <option value="asc">正序（最早在前）</option>
          </select>
        </label>
      </div>

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
          {visibleDecisions.map((decision) => {
            const localizedReasonSummary =
              localizeResearchReason(decision.reasonSummary) || "当前没有额外原因摘要。";
            const localizedAuditReason =
              localizeResearchReason(decision.audit?.reasonSummary) || null;
            const localizedFallbackReason =
              localizeResearchReason(decision.audit?.fallbackReason) || null;
            const skipReasonDetail = describeResearchSkipReason(decision);
            const executionPlanLabel =
              decision.executionAction === "SKIP" && decision.orderPlanSide === null
                ? "跳过（未生成可执行订单）"
                : titleCase(decision.executionAction);

            return (
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
                    <strong>{localizedReasonSummary}</strong>
                    {decision.audit ? (
                      <>
                        <span>{`来源：${formatAuditProvider(decision.audit.providerId)}`}</span>
                        <span>{`审计决策：${titleCase(decision.audit.decision || "--")}`}</span>
                        {decision.audit.confidence ? (
                          <span>{`置信度：${decision.audit.confidence}`}</span>
                        ) : null}
                        {localizedAuditReason && localizedAuditReason !== localizedReasonSummary ? (
                          <span>{`审计摘要：${localizedAuditReason}`}</span>
                        ) : null}
                        {decision.audit.fallbackUsed ? (
                          <span>{`回退原因：${localizedFallbackReason || "外部 provider 暂不可用"}`}</span>
                        ) : null}
                      </>
                    ) : null}
                    {decision.skipReason ? (
                      <>
                        <span>跳过原因：{titleCase(decision.skipReason)}</span>
                        {skipReasonDetail ? <span>{`跳过说明：${skipReasonDetail}`}</span> : null}
                        <span>{`原因代码：${decision.skipReason}`}</span>
                      </>
                    ) : null}
                    <span>{`下单计划：${executionPlanLabel}`}</span>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {pageCount > 1 ? (
        <div className="decision-pagination">
          <p className="decision-pagination__summary" aria-live="polite">
            {`第 ${page + 1} / ${pageCount} 页 · 显示第 ${startIndex + 1}-${endIndex} 条，共 ${sortedDecisions.length} 条`}
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
          <form
            className="decision-pagination__jump"
            onSubmit={(event) => {
              event.preventDefault();
              jumpToPage();
            }}
          >
            <label className="decision-pagination__jump-label">
              跳到第
              <input
                type="number"
                min={1}
                max={pageCount}
                step={1}
                inputMode="numeric"
                className="decision-pagination__jump-input"
                aria-label="跳到第几页"
                value={pageInput}
                onChange={(event) => setPageInput(event.target.value)}
              />
              页
            </label>
            <button
              type="submit"
              className="secondary-button"
              disabled={pageInput.trim().length === 0}
            >
              跳转
            </button>
          </form>
        </div>
      ) : null}
    </div>
  );
}
