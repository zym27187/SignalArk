import { useEffect, useState } from "react";

import { ViewSwitcher } from "./components/ViewSwitcher";
import { MarketView } from "./components/views/MarketView";
import { OperationsView } from "./components/views/OperationsView";
import { ResearchView } from "./components/views/ResearchView";
import { useHashView } from "./hooks/use-hash-view";
import { useDashboardData } from "./hooks/use-dashboard-data";
import { useMarketData } from "./hooks/use-market-data";
import { useResearchData } from "./hooks/use-research-data";
import {
  DEFAULT_RULE_RESEARCH_HISTORY_YEARS,
  type RuleResearchHistoryYears,
} from "./lib/api";
import { formatDateTime } from "./lib/format";
import type { SymbolNameMap } from "./types/api";
import type { ResearchMode } from "./types/research";

const DEFAULT_SYMBOL_NAMES: SymbolNameMap = {
  "600036.SH": "招商银行",
  "000001.SZ": "平安银行",
};
const DEFAULT_SYMBOL_OPTIONS = Object.keys(DEFAULT_SYMBOL_NAMES);
const MARKET_TIMEFRAME_OPTIONS = ["15m", "1h"];
const RESEARCH_TIMEFRAME_OPTIONS = ["15m", "1h", "1d"];

export default function App() {
  const dashboard = useDashboardData();
  const { view, navigate } = useHashView();
  const availableSymbols =
    dashboard.snapshot.status?.symbols && dashboard.snapshot.status.symbols.length > 0
      ? dashboard.snapshot.status.symbols
      : DEFAULT_SYMBOL_OPTIONS;
  const symbolNames = {
    ...DEFAULT_SYMBOL_NAMES,
    ...(dashboard.snapshot.status?.symbol_names ?? {}),
  };
  const [selectedSymbol, setSelectedSymbol] = useState<string>(
    availableSymbols[0] ?? DEFAULT_SYMBOL_OPTIONS[0],
  );
  const [selectedMarketTimeframe, setSelectedMarketTimeframe] = useState<string>(
    MARKET_TIMEFRAME_OPTIONS[0],
  );
  const [selectedResearchTimeframe, setSelectedResearchTimeframe] = useState<string>(
    RESEARCH_TIMEFRAME_OPTIONS[0],
  );
  const [selectedResearchMode, setSelectedResearchMode] =
    useState<ResearchMode>("evaluation");
  const [selectedRuleHistoryYears, setSelectedRuleHistoryYears] =
    useState<RuleResearchHistoryYears>(DEFAULT_RULE_RESEARCH_HISTORY_YEARS);

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
    mode: selectedResearchMode,
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
      ? "更新中..."
      : "刷新内容";

  function renderView() {
    switch (view) {
      case "market":
        return (
          <MarketView
            status={dashboard.snapshot.status}
            marketData={marketData}
            availableSymbols={availableSymbols}
            symbolNames={symbolNames}
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
            symbolNames={symbolNames}
            availableTimeframes={RESEARCH_TIMEFRAME_OPTIONS}
            selectedSymbol={selectedSymbol}
            selectedTimeframe={selectedResearchTimeframe}
            selectedMode={selectedResearchMode}
            selectedRuleHistoryYears={selectedRuleHistoryYears}
            onSymbolChange={setSelectedSymbol}
            onTimeframeChange={setSelectedResearchTimeframe}
            onModeChange={setSelectedResearchMode}
            onRuleHistoryYearsChange={setSelectedRuleHistoryYears}
          />
        );
      case "operations":
      default:
        return (
          <OperationsView
            dashboard={dashboard}
            symbolNames={symbolNames}
          />
        );
    }
  }

  return (
    <div className="app-shell">
      <div className="app-shell__background" />

      <header className="masthead">
        <div className="masthead__copy">
          <p className="masthead__eyebrow">模拟交易 / 交易总览</p>
          <h1 className="masthead__title">SignalArk 交易看板</h1>
          <p className="masthead__summary">
            把交易状态、市场走势和回测结果放到同一个页面里，方便快速看清现在发生了什么。
          </p>
        </div>

        <div className="masthead__actions">
          <div className="masthead__meta">
            <span className="mini-label">最近更新</span>
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
