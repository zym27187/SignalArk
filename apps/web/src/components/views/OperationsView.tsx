import { useDeferredValue } from "react";

import { ActivityFiltersPanel } from "../ActivityFiltersPanel";
import { BalanceSummaryPanel } from "../BalanceSummaryPanel";
import { ControlPanel } from "../ControlPanel";
import { EventTimeline } from "../EventTimeline";
import { FillHistoryTable } from "../FillHistoryTable";
import { MetricCard } from "../MetricCard";
import { OrderHistoryTable } from "../OrderHistoryTable";
import { OrdersTable } from "../OrdersTable";
import { PositionsTable } from "../PositionsTable";
import { SectionCard } from "../SectionCard";
import { SymbolInspectorPanel } from "../SymbolInspectorPanel";
import { StatusHero } from "../StatusHero";
import { TradingGlossaryPanel } from "../TradingGlossaryPanel";
import { compactId, titleCase } from "../../lib/format";
import type { DashboardDataState } from "../../hooks/use-dashboard-data";
import type { SymbolNameMap } from "../../types/api";

function controlTone(
  controlState: string | undefined,
): "default" | "positive" | "warning" | "danger" {
  if (controlState === "kill_switch" || controlState === "protection_mode") {
    return "danger";
  }

  if (controlState === "normal") {
    return "positive";
  }

  return "warning";
}

interface OperationsViewProps {
  dashboard: DashboardDataState;
  symbolNames: SymbolNameMap;
}

export function OperationsView({ dashboard, symbolNames }: OperationsViewProps) {
  const deferredEvents = useDeferredValue(dashboard.snapshot.events);
  const status = dashboard.snapshot.status;
  const availableSymbols = status?.symbols ?? [];

  return (
    <main className="page-stack">
      <StatusHero
        status={status}
        isLoading={dashboard.isLoading}
        error={dashboard.snapshot.sectionErrors.status}
      />

      <section className="metric-grid">
        <MetricCard
          label="运行准备"
          value={status?.ready ? "可以运行" : "等待中"}
          hint={`系统状态：${titleCase(status?.status)}`}
          tone={status?.ready ? "positive" : "warning"}
        />
        <MetricCard
          label="控制状态"
          value={titleCase(status?.control_state)}
          hint={status?.strategy_enabled ? "自动下单已开启" : "自动下单已暂停"}
          tone={controlTone(status?.control_state)}
        />
        <MetricCard
          label="行情更新"
          value={status?.market_data_fresh ? "已更新" : "待更新"}
          hint={`当前时段：${titleCase(status?.current_trading_phase)}`}
          tone={status?.market_data_fresh ? "positive" : "warning"}
        />
        <MetricCard
          label="当前控制编号"
          value={status?.fencing_token ?? "--"}
          hint={`当前由 ${compactId(status?.lease_owner_instance_id)} 持有`}
          tone="default"
        />
      </section>

      <section className="interaction-hub">
        <SectionCard
          className="interaction-hub__card"
          eyebrow="控制台入口"
          title="手动操作"
          description="先决定系统要不要继续自动动作，高风险操作会在这里集中确认。"
        >
          <ControlPanel
            status={status}
            pendingAction={dashboard.pendingAction}
            lastActionResult={dashboard.lastActionResult}
            onAction={dashboard.performAction}
          />
        </SectionCard>

        <SectionCard
          className="interaction-hub__card"
          eyebrow="控制台入口"
          title="筛选条件"
          description="先把查看范围收口，下面订单、成交和事件时间线会一起跟着变化。"
        >
          <ActivityFiltersPanel
            filters={dashboard.activityFilters}
            availableSymbols={availableSymbols}
            symbolNames={symbolNames}
            isRefreshing={dashboard.isRefreshing}
            onApply={dashboard.applyActivityFilters}
            onReset={dashboard.resetActivityFilters}
          />
        </SectionCard>

        <SectionCard
          className="interaction-hub__card"
          eyebrow="控制台入口"
          title="股票代码管理"
          description="在同一块交互区里完成代码检查、层级确认和运行范围申请判断。"
        >
          <SymbolInspectorPanel runtimeSymbols={availableSymbols} symbolNames={symbolNames} />
        </SectionCard>
      </section>

      <SectionCard
        eyebrow="账户"
        title="资金与权益"
        description="先看账户概览中的核心数字，再往下查看全量持仓明细。"
      >
        <BalanceSummaryPanel
          summary={dashboard.snapshot.balanceSummary}
          error={dashboard.snapshot.sectionErrors.balanceSummary}
        />
      </SectionCard>

      <SectionCard
        eyebrow="账户"
        title="当前持仓"
        description="全宽展示当前持仓明细；没有持仓时只保留紧凑空状态，不再单独占一列。"
      >
        <PositionsTable
          positions={dashboard.snapshot.positions}
          symbolNames={symbolNames}
          error={dashboard.snapshot.sectionErrors.positions}
        />
      </SectionCard>

      <section className="operations-flow">
        <SectionCard
          eyebrow="进行中"
          title="未完成订单"
          description="这里看还在排队、已接收或部分成交的订单。"
        >
          <OrdersTable
            orders={dashboard.snapshot.orders}
            symbolNames={symbolNames}
            error={dashboard.snapshot.sectionErrors.orders}
          />
        </SectionCard>

        <SectionCard
          eyebrow="回看"
          title="历史订单"
          description="这里按筛选回看订单从提交到结束的全过程。"
        >
          <OrderHistoryTable
            orders={dashboard.snapshot.orderHistory}
            symbolNames={symbolNames}
            error={dashboard.snapshot.sectionErrors.orderHistory}
          />
        </SectionCard>

        <SectionCard
          eyebrow="回看"
          title="历史成交"
          description="这里看已经真正成交的记录，不用再手动查库。"
        >
          <FillHistoryTable
            fills={dashboard.snapshot.fills}
            symbolNames={symbolNames}
            error={dashboard.snapshot.sectionErrors.fillHistory}
          />
        </SectionCard>

        <SectionCard
          className="operations-flow__events"
          eyebrow="最近动态"
          title="最近发生了什么"
          description="按当前筛选展示最近的关键事件时间线。"
        >
          <EventTimeline
            events={deferredEvents}
            symbolNames={symbolNames}
            error={dashboard.snapshot.sectionErrors.events}
          />
        </SectionCard>

        <SectionCard
          className="operations-flow__glossary"
          eyebrow="名词解释"
          title="常见术语"
          description="把常见交易术语收进可折叠区域，需要时再展开查看。"
        >
          <details className="operations-fold">
            <summary className="operations-fold__summary">查看术语解释</summary>
            <div className="operations-fold__body">
              <TradingGlossaryPanel />
            </div>
          </details>
        </SectionCard>
      </section>
    </main>
  );
}
