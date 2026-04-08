import { useDeferredValue } from "react";

import { ActivityFiltersPanel } from "../ActivityFiltersPanel";
import { ControlPanel } from "../ControlPanel";
import { EventTimeline } from "../EventTimeline";
import { FillHistoryTable } from "../FillHistoryTable";
import { MetricCard } from "../MetricCard";
import { OrderHistoryTable } from "../OrderHistoryTable";
import { OrdersTable } from "../OrdersTable";
import { PositionsTable } from "../PositionsTable";
import { SectionCard } from "../SectionCard";
import { StatusHero } from "../StatusHero";
import { compactId, titleCase } from "../../lib/format";
import type { DashboardDataState } from "../../hooks/use-dashboard-data";

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
}

export function OperationsView({ dashboard }: OperationsViewProps) {
  const deferredEvents = useDeferredValue(dashboard.snapshot.events);
  const status = dashboard.snapshot.status;
  const availableSymbols = status?.symbols ?? [];

  return (
    <main className="dashboard-grid">
      <div className="dashboard-grid__primary">
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

        <SectionCard
          eyebrow="账户"
          title="当前持仓"
          description="这里看账户里还持有哪些仓位，以及它们现在的盈亏。"
        >
          <PositionsTable
            positions={dashboard.snapshot.positions}
            error={dashboard.snapshot.sectionErrors.positions}
          />
        </SectionCard>

        <SectionCard
          eyebrow="进行中"
          title="未完成订单"
          description="这里看还在排队、已接收或部分成交的订单。"
        >
          <OrdersTable
            orders={dashboard.snapshot.orders}
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
            error={dashboard.snapshot.sectionErrors.fillHistory}
          />
        </SectionCard>
      </div>

      <aside className="dashboard-grid__rail">
        <SectionCard
          eyebrow="人工操作"
          title="手动操作"
          description="需要人工介入时，可以在这里暂停、恢复或撤单。"
        >
          <ControlPanel
            status={status}
            pendingAction={dashboard.pendingAction}
            lastActionResult={dashboard.lastActionResult}
            onAction={dashboard.performAction}
          />
        </SectionCard>

        <SectionCard
          eyebrow="查看范围"
          title="筛选条件"
          description="设置时间、标的和状态后，下面各块会一起切到同一批数据。"
        >
          <ActivityFiltersPanel
            filters={dashboard.activityFilters}
            availableSymbols={availableSymbols}
            isRefreshing={dashboard.isRefreshing}
            onApply={dashboard.applyActivityFilters}
            onReset={dashboard.resetActivityFilters}
          />
        </SectionCard>

        <SectionCard
          eyebrow="最近动态"
          title="最近发生了什么"
          description="按当前筛选展示最近的关键事件时间线。"
        >
          <EventTimeline
            events={deferredEvents}
            error={dashboard.snapshot.sectionErrors.events}
          />
        </SectionCard>
      </aside>
    </main>
  );
}
