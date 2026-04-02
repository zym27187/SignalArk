import { useDeferredValue } from "react";

import { ControlPanel } from "../ControlPanel";
import { EventTimeline } from "../EventTimeline";
import { MetricCard } from "../MetricCard";
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
            label="Ready State"
            value={status?.ready ? "Ready" : "Standby"}
            hint={titleCase(status?.status)}
            tone={status?.ready ? "positive" : "warning"}
          />
          <MetricCard
            label="Control State"
            value={titleCase(status?.control_state)}
            hint={status?.strategy_enabled ? "Strategy enabled" : "Strategy paused by operator"}
            tone={controlTone(status?.control_state)}
          />
          <MetricCard
            label="Market Feed"
            value={status?.market_data_fresh ? "Fresh" : "Stale"}
            hint={titleCase(status?.current_trading_phase)}
            tone={status?.market_data_fresh ? "positive" : "warning"}
          />
          <MetricCard
            label="Lease Token"
            value={status?.fencing_token ?? "--"}
            hint={`Owner ${compactId(status?.lease_owner_instance_id)}`}
            tone="default"
          />
        </section>

        <SectionCard
          eyebrow="Portfolio"
          title="Open Positions"
          description="Current persisted position state as seen by the control plane."
        >
          <PositionsTable
            positions={dashboard.snapshot.positions}
            error={dashboard.snapshot.sectionErrors.positions}
          />
        </SectionCard>

        <SectionCard
          eyebrow="Execution"
          title="Active Orders"
          description="Live order queue surface for operator review and cancel-all actions."
        >
          <OrdersTable
            orders={dashboard.snapshot.orders}
            error={dashboard.snapshot.sectionErrors.orders}
          />
        </SectionCard>
      </div>

      <aside className="dashboard-grid__rail">
        <SectionCard
          eyebrow="Operator"
          title="Control Actions"
          description="Manual interventions should stay visible, explicit, and reversible."
        >
          <ControlPanel
            status={status}
            pendingAction={dashboard.pendingAction}
            actionMessage={dashboard.actionMessage}
            onAction={dashboard.performAction}
          />
        </SectionCard>

        <SectionCard
          eyebrow="Diagnostics"
          title="Recent Event Replay"
          description="A compact audit rail sourced from the reconciliation replay endpoint."
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
