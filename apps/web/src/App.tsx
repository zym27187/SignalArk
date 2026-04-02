import { ViewSwitcher } from "./components/ViewSwitcher";
import { MarketView } from "./components/views/MarketView";
import { OperationsView } from "./components/views/OperationsView";
import { ResearchView } from "./components/views/ResearchView";
import { useHashView } from "./hooks/use-hash-view";
import { useDashboardData } from "./hooks/use-dashboard-data";
import { formatDateTime } from "./lib/format";

export default function App() {
  const dashboard = useDashboardData();
  const { view, navigate } = useHashView();

  function renderView() {
    switch (view) {
      case "market":
        return <MarketView status={dashboard.snapshot.status} />;
      case "research":
        return <ResearchView />;
      case "operations":
      default:
        return <OperationsView dashboard={dashboard} />;
    }
  }

  return (
    <div className="app-shell">
      <div className="app-shell__background" />

      <header className="masthead">
        <div className="masthead__copy">
          <p className="masthead__eyebrow">Paper Trading / Control Plane / Phase 1</p>
          <h1 className="masthead__title">SignalArk Console</h1>
          <p className="masthead__summary">
            A multi-view frontend shell for operator supervision, market visualization, and
            research output review.
          </p>
        </div>

        <div className="masthead__actions">
          <div className="masthead__meta">
            <span className="mini-label">Last Refresh</span>
            <strong>{formatDateTime(dashboard.snapshot.fetchedAt)}</strong>
          </div>
          <button
            type="button"
            className="refresh-button"
            onClick={() => {
              void dashboard.refresh();
            }}
            disabled={dashboard.isRefreshing}
          >
            {dashboard.isRefreshing ? "Refreshing..." : "Refresh Snapshot"}
          </button>
        </div>
      </header>

      <div className="app-frame">
        <ViewSwitcher
          value={view}
          onChange={navigate}
        />
        {renderView()}
      </div>
    </div>
  );
}
