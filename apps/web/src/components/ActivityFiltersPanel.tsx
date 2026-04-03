import { useEffect, useState } from "react";

import { titleCase } from "../lib/format";
import type { DashboardActivityFilters } from "../types/api";

const LIMIT_OPTIONS = [12, 25, 50, 100];
const ORDER_STATUS_OPTIONS = [
  "NEW",
  "ACK",
  "PARTIALLY_FILLED",
  "FILLED",
  "CANCELED",
  "REJECTED",
];

interface ActivityFiltersPanelProps {
  filters: DashboardActivityFilters;
  availableSymbols: string[];
  isRefreshing: boolean;
  onApply: (filters: DashboardActivityFilters) => Promise<void> | void;
  onReset: () => Promise<void> | void;
}

export function ActivityFiltersPanel({
  filters,
  availableSymbols,
  isRefreshing,
  onApply,
  onReset,
}: ActivityFiltersPanelProps) {
  const [draft, setDraft] = useState(filters);

  useEffect(() => {
    setDraft(filters);
  }, [filters]);

  return (
    <form
      className="filter-form"
      onSubmit={(event) => {
        event.preventDefault();
        void onApply(draft);
      }}
    >
      <div className="filter-form__grid">
        <label className="filter-form__field">
          <span>标的</span>
          <select
            value={draft.symbol}
            onChange={(event) => {
              setDraft((previous) => ({
                ...previous,
                symbol: event.target.value,
              }));
            }}
          >
            <option value="">全部标的</option>
            {availableSymbols.map((symbol) => (
              <option
                key={symbol}
                value={symbol}
              >
                {symbol}
              </option>
            ))}
          </select>
        </label>

        <label className="filter-form__field">
          <span>订单状态</span>
          <select
            value={draft.status}
            onChange={(event) => {
              setDraft((previous) => ({
                ...previous,
                status: event.target.value,
              }));
            }}
          >
            <option value="">全部状态</option>
            {ORDER_STATUS_OPTIONS.map((status) => (
              <option
                key={status}
                value={status}
              >
                {titleCase(status)}
              </option>
            ))}
          </select>
        </label>

        <label className="filter-form__field">
          <span>Order ID</span>
          <input
            type="text"
            placeholder="可选，输入完整订单 UUID"
            value={draft.orderId}
            onChange={(event) => {
              setDraft((previous) => ({
                ...previous,
                orderId: event.target.value,
              }));
            }}
          />
        </label>

        <label className="filter-form__field">
          <span>Trader Run ID</span>
          <input
            type="text"
            placeholder="可选，输入完整 UUID"
            value={draft.traderRunId}
            onChange={(event) => {
              setDraft((previous) => ({
                ...previous,
                traderRunId: event.target.value,
              }));
            }}
          />
        </label>

        <label className="filter-form__field">
          <span>开始时间</span>
          <input
            type="datetime-local"
            value={draft.startTime}
            onChange={(event) => {
              setDraft((previous) => ({
                ...previous,
                startTime: event.target.value,
              }));
            }}
          />
        </label>

        <label className="filter-form__field">
          <span>结束时间</span>
          <input
            type="datetime-local"
            value={draft.endTime}
            onChange={(event) => {
              setDraft((previous) => ({
                ...previous,
                endTime: event.target.value,
              }));
            }}
          />
        </label>

        <label className="filter-form__field">
          <span>返回条数</span>
          <select
            value={String(draft.limit)}
            onChange={(event) => {
              setDraft((previous) => ({
                ...previous,
                limit: Number(event.target.value),
              }));
            }}
          >
            {LIMIT_OPTIONS.map((limit) => (
              <option
                key={limit}
                value={limit}
              >
                {limit}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="filter-form__actions">
        <button
          type="submit"
          className="filter-form__button filter-form__button--primary"
          disabled={isRefreshing}
        >
          {isRefreshing ? "应用中..." : "应用筛选"}
        </button>
        <button
          type="button"
          className="filter-form__button"
          disabled={isRefreshing}
          onClick={() => {
            void onReset();
          }}
        >
          清空筛选
        </button>
      </div>

      <p className="filter-form__hint">
        `symbol`、`trader_run_id`、时间窗和条数会联动全部视图；`订单状态` 只作用于历史订单，`Order ID` 只作用于历史成交。
      </p>
    </form>
  );
}
