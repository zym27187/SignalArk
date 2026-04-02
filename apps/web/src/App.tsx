import { useEffect, useState } from "react";

import { ViewSwitcher } from "./components/ViewSwitcher";
import { MarketView } from "./components/views/MarketView";
import { OperationsView } from "./components/views/OperationsView";
import { ResearchView } from "./components/views/ResearchView";
import { useHashView } from "./hooks/use-hash-view";
import { useDashboardData } from "./hooks/use-dashboard-data";
import { useMarketData } from "./hooks/use-market-data";
import { useResearchData } from "./hooks/use-research-data";
import { formatDateTime } from "./lib/format";

const DEFAULT_SYMBOL_OPTIONS = ["600036.SH", "000001.SZ"];
const MARKET_TIMEFRAME_OPTIONS = ["15m", "1h"];
const RESEARCH_TIMEFRAME_OPTIONS = ["15m", "1h"];

export default function App() {
  const dashboard = useDashboardData();
  const { view, navigate } = useHashView();
  const availableSymbols =
    dashboard.snapshot.status?.symbols && dashboard.snapshot.status.symbols.length > 0
      ? dashboard.snapshot.status.symbols
      : DEFAULT_SYMBOL_OPTIONS;
  const [selectedSymbol, setSelectedSymbol] = useState<string>(
    availableSymbols[0] ?? DEFAULT_SYMBOL_OPTIONS[0],
  );
  const [selectedMarketTimeframe, setSelectedMarketTimeframe] = useState<string>(
    MARKET_TIMEFRAME_OPTIONS[0],
  );
  const [selectedResearchTimeframe, setSelectedResearchTimeframe] = useState<string>(
    RESEARCH_TIMEFRAME_OPTIONS[0],
  );

  useEffect(() => {
    if (!availableSymbols.includes(selectedSymbol)) {
      setSelectedSymbol(availableSymbols[0] ?? DEFAULT_SYMBOL_OPTIONS[0]);
    }
  }, [availableSymbols, selectedSymbol]);

  useEffect(() => {
    if (!RESEARCH_TIMEFRAME_OPTIONS.includes(selectedResearchTimeframe)) {
      setSelectedResearchTimeframe(RESEARCH_TIMEFRAME_OPTIONS[0] ?? "15m");
    }
  }, [selectedResearchTimeframe]);

  const marketData = useMarketData({
    enabled: view === "market",
    symbol: selectedSymbol,
    timeframe: selectedMarketTimeframe,
  });
  const researchData = useResearchData({
    enabled: view === "research",
    symbol: selectedSymbol,
    timeframe: selectedResearchTimeframe,
  });

  const activeFetchedAt =
    view === "research"
      ? researchData.fetchedAt ?? dashboard.snapshot.fetchedAt
      : view === "market"
        ? marketData.snapshot.fetchedAt ?? dashboard.snapshot.fetchedAt
        : dashboard.snapshot.fetchedAt;
  const refreshDisabled =
    dashboard.isRefreshing
    || (view === "market" && marketData.isRefreshing)
    || (view === "research" && researchData.isRefreshing);
  const refreshLabel =
    dashboard.isRefreshing
    || (view === "market" && marketData.isRefreshing)
    || (view === "research" && researchData.isRefreshing)
      ? "刷新中..."
      : "刷新快照";

  function renderView() {
    switch (view) {
      case "market":
        return (
          <MarketView
            status={dashboard.snapshot.status}
            marketData={marketData}
            availableSymbols={availableSymbols}
            availableTimeframes={MARKET_TIMEFRAME_OPTIONS}
            selectedSymbol={selectedSymbol}
            selectedTimeframe={selectedMarketTimeframe}
            onSymbolChange={setSelectedSymbol}
            onTimeframeChange={setSelectedMarketTimeframe}
          />
        );
      case "research":
        return (
          <ResearchView
            researchData={researchData}
            availableSymbols={availableSymbols}
            availableTimeframes={RESEARCH_TIMEFRAME_OPTIONS}
            selectedSymbol={selectedSymbol}
            selectedTimeframe={selectedResearchTimeframe}
            onSymbolChange={setSelectedSymbol}
            onTimeframeChange={setSelectedResearchTimeframe}
          />
        );
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
            <strong>{formatDateTime(activeFetchedAt)}</strong>
          </div>
          <button
            type="button"
            className="refresh-button"
            onClick={async () => {
              void dashboard.refresh();
              if (view === "market") {
                void marketData.refresh();
              }
              if (view === "research") {
                void researchData.refresh();
              }
            }}
            disabled={refreshDisabled}
          >
            {refreshLabel}
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
