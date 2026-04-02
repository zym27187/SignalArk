import { ViewSwitcher } from "./components/ViewSwitcher";
import { MarketView } from "./components/views/MarketView";
import { OperationsView } from "./components/views/OperationsView";
import { ResearchView } from "./components/views/ResearchView";
import { useHashView } from "./hooks/use-hash-view";
import { useDashboardData } from "./hooks/use-dashboard-data";
import { useMarketData } from "./hooks/use-market-data";
import { formatDateTime } from "./lib/format";

export default function App() {
  const dashboard = useDashboardData();
  const { view, navigate } = useHashView();
  const marketData = useMarketData({
    enabled: view === "market",
    symbol: dashboard.snapshot.status?.symbols?.[0] ?? null,
  });

  function renderView() {
    switch (view) {
      case "market":
        return (
          <MarketView
            status={dashboard.snapshot.status}
            marketData={marketData}
          />
        );
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
          <p className="masthead__eyebrow">模拟交易 / 控制平面 / 第一阶段</p>
          <h1 className="masthead__title">SignalArk 控制台</h1>
          <p className="masthead__summary">
            用于运维值守、市场可视化与研究结果复核的多视图前端控制台。
          </p>
        </div>

        <div className="masthead__actions">
          <div className="masthead__meta">
            <span className="mini-label">最近刷新</span>
            <strong>{formatDateTime(dashboard.snapshot.fetchedAt)}</strong>
          </div>
          <button
            type="button"
            className="refresh-button"
            onClick={async () => {
              void dashboard.refresh();
              if (view === "market") {
                void marketData.refresh();
              }
            }}
            disabled={dashboard.isRefreshing || (view === "market" && marketData.isRefreshing)}
          >
            {dashboard.isRefreshing || (view === "market" && marketData.isRefreshing)
              ? "刷新中..."
              : "刷新快照"}
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
