import { useDeferredValue } from "react";

import { ControlPanel } from "./components/ControlPanel";
import { EventTimeline } from "./components/EventTimeline";
import { MetricCard } from "./components/MetricCard";
import { OrdersTable } from "./components/OrdersTable";
import { PositionsTable } from "./components/PositionsTable";
import { SectionCard } from "./components/SectionCard";
import { StatusHero } from "./components/StatusHero";
import { compactId, formatDateTime, titleCase } from "./lib/format";
import { useDashboardData } from "./hooks/use-dashboard-data";

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

export default function App() {
  const {
    snapshot,
    isLoading,
    isRefreshing,
    pendingAction,
    actionMessage,
    refresh,
    performAction,
  } = useDashboardData();

  const deferredEvents = useDeferredValue(snapshot.events);
  const status = snapshot.status;

  return (
    <div className="app-shell">
      <div className="app-shell__background" />

      <header className="masthead">
        <div className="masthead__copy">
          <p className="masthead__eyebrow">Paper Trading / Control Plane / Phase 1</p>
          <h1 className="masthead__title">SignalArk Console Skeleton</h1>
          <p className="masthead__summary">
            A frontend shell for runtime supervision, operator controls, and event replay.
          </p>
        </div>

        <div className="masthead__actions">
          <div className="masthead__meta">
            <span className="mini-label">Last Refresh</span>
            <strong>{formatDateTime(snapshot.fetchedAt)}</strong>
          </div>
          <button
            type="button"
            className="refresh-button"
            onClick={() => {
              void refresh();
            }}
            disabled={isRefreshing}
          >
            {isRefreshing ? "Refreshing..." : "Refresh Snapshot"}
          </button>
        </div>
      </header>

      <main className="dashboard-grid">
        <div className="dashboard-grid__primary">
          <StatusHero
            status={status}
            isLoading={isLoading}
            error={snapshot.sectionErrors.status}
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
              hint={
                status?.strategy_enabled ? "Strategy enabled" : "Strategy paused by operator"
              }
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
              positions={snapshot.positions}
              error={snapshot.sectionErrors.positions}
            />
          </SectionCard>

          <SectionCard
            eyebrow="Execution"
            title="Active Orders"
            description="Live order queue surface for operator review and cancel-all actions."
          >
            <OrdersTable
              orders={snapshot.orders}
              error={snapshot.sectionErrors.orders}
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
              pendingAction={pendingAction}
              actionMessage={actionMessage}
              onAction={performAction}
            />
          </SectionCard>

          <SectionCard
            eyebrow="Diagnostics"
            title="Recent Event Replay"
            description="A compact audit rail sourced from the reconciliation replay endpoint."
          >
            <EventTimeline
              events={deferredEvents}
              error={snapshot.sectionErrors.events}
            />
          </SectionCard>
        </aside>
      </main>
    </div>
  );
}

