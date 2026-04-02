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
            label="就绪状态"
            value={status?.ready ? "就绪" : "待命"}
            hint={titleCase(status?.status)}
            tone={status?.ready ? "positive" : "warning"}
          />
          <MetricCard
            label="控制状态"
            value={titleCase(status?.control_state)}
            hint={status?.strategy_enabled ? "策略已启用" : "策略已被操作员暂停"}
            tone={controlTone(status?.control_state)}
          />
          <MetricCard
            label="行情数据"
            value={status?.market_data_fresh ? "最新" : "过期"}
            hint={titleCase(status?.current_trading_phase)}
            tone={status?.market_data_fresh ? "positive" : "warning"}
          />
          <MetricCard
            label="租约令牌"
            value={status?.fencing_token ?? "--"}
            hint={`持有者 ${compactId(status?.lease_owner_instance_id)}`}
            tone="default"
          />
        </section>

        <SectionCard
          eyebrow="组合"
          title="当前持仓"
          description="控制平面当前看到的已持久化持仓状态。"
        >
          <PositionsTable
            positions={dashboard.snapshot.positions}
            error={dashboard.snapshot.sectionErrors.positions}
          />
        </SectionCard>

        <SectionCard
          eyebrow="执行"
          title="活动订单"
          description="供人工复核与一键撤单的实时订单队列。"
        >
          <OrdersTable
            orders={dashboard.snapshot.orders}
            error={dashboard.snapshot.sectionErrors.orders}
          />
        </SectionCard>

        <SectionCard
          eyebrow="执行复核"
          title="历史订单"
          description="按当前筛选回看订单状态流转、风控裁决和最终结果。"
        >
          <OrderHistoryTable
            orders={dashboard.snapshot.orderHistory}
            error={dashboard.snapshot.sectionErrors.orderHistory}
          />
        </SectionCard>

        <SectionCard
          eyebrow="执行复核"
          title="历史成交"
          description="按当前筛选查看已持久化 fills，减少人工直查数据库。"
        >
          <FillHistoryTable
            fills={dashboard.snapshot.fills}
            error={dashboard.snapshot.sectionErrors.fillHistory}
          />
        </SectionCard>
      </div>

      <aside className="dashboard-grid__rail">
        <SectionCard
          eyebrow="操作员"
          title="控制动作"
          description="人工干预应保持可见、明确且可回退。"
        >
          <ControlPanel
            status={status}
            pendingAction={dashboard.pendingAction}
            actionMessage={dashboard.actionMessage}
            onAction={dashboard.performAction}
          />
        </SectionCard>

        <SectionCard
          eyebrow="筛选"
          title="执行与诊断筛选"
          description="同一组筛选会同步作用于历史订单、历史成交和事件回放。"
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
          eyebrow="诊断"
          title="近期事件回放"
          description="基于当前筛选上下文返回的审计时间线。"
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
