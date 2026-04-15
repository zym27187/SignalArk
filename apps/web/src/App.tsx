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
import { formatDateTime, formatSymbolLabel, titleCase } from "./lib/format";
import type { SymbolNameMap } from "./types/api";
import type { AppView, ResearchMode } from "./types/research";

const DEFAULT_SYMBOL_NAMES: SymbolNameMap = {
  "600036.SH": "招商银行",
  "000001.SZ": "平安银行",
};
const DEFAULT_SYMBOL_OPTIONS = Object.keys(DEFAULT_SYMBOL_NAMES);
const MARKET_TIMEFRAME_OPTIONS = ["15m", "1h"];
const RESEARCH_TIMEFRAME_OPTIONS = ["15m", "1h", "1d"];
const VIEW_META: Record<
  AppView,
  {
    eyebrow: string;
    title: string;
    summary: string;
  }
> = {
  operations: {
    eyebrow: "运行控制",
    title: "运行状态与控制操作",
    summary: "集中查看系统状态、账户信息、订单记录与人工控制入口。",
  },
  market: {
    eyebrow: "市场监控",
    title: "行情走势与运行诊断",
    summary: "在统一上下文中查看价格走势、权益曲线与运行诊断数据。",
  },
  research: {
    eyebrow: "研究分析",
    title: "回测结果与策略评估",
    summary: "基于选定标的与周期查看回测表现、参数配置与决策明细。",
  },
};

function formatResearchModeLabel(mode: ResearchMode): string {
  switch (mode) {
    case "preview":
      return "快速预览";
    case "parameter_scan":
      return "参数扫描";
    case "walk_forward":
      return "滚动评估";
    case "evaluation":
    default:
      return "评估样本";
  }
}

function describeReadiness(status: ReturnType<typeof useDashboardData>["snapshot"]["status"]) {
  if (!status) {
    return {
      tone: "warning",
      label: "等待状态接通",
      hint: "状态接口恢复前，不要默认系统仍在正常自动运行。",
    };
  }

  if (status.ready) {
    return {
      tone: "positive",
      label: "可以运行",
      hint: status.strategy_enabled
        ? "自动策略已开启，可以继续把当前页面当成主控制台。"
        : "系统已就绪，但自动策略当前仍处于暂停状态。",
    };
  }

  return {
    tone: "warning",
    label: "等待检查",
    hint: "先确认 readiness、行情 freshness 和控制状态，再决定是否继续自动运行。",
  };
}

function describeControlState(status: ReturnType<typeof useDashboardData>["snapshot"]["status"]) {
  if (!status) {
    return {
      tone: "warning",
      label: "尚未确认",
      hint: "当前还不能确认在线控制面是否可用。",
    };
  }

  if (status.control_state === "kill_switch" || status.control_state === "protection_mode") {
    return {
      tone: "danger",
      label: titleCase(status.control_state),
      hint: "系统处于强保护状态，新的开仓动作会被限制。",
    };
  }

  return {
    tone: "default",
    label: titleCase(status.control_state),
    hint: status.strategy_enabled
      ? "人工动作会直接影响在线控制服务。"
      : "自动下单当前已暂停，但页面仍可用于人工值守和复盘。",
  };
}

function describeFocus(
  view: AppView,
  symbolLabel: string,
  marketTimeframe: string,
  researchTimeframe: string,
  researchMode: ResearchMode,
  accountId: string | null | undefined,
) {
  if (view === "market") {
    return {
      tone: "default",
      label: `${symbolLabel} · ${marketTimeframe}`,
      hint: "价格走势、账户曲线和 runtime audit 都会跟着这个上下文走。",
    };
  }

  if (view === "research") {
    return {
      tone: "default",
      label: `${symbolLabel} · ${researchTimeframe}`,
      hint: `${formatResearchModeLabel(researchMode)}已选中，下面的研究结果会按同一上下文刷新。`,
    };
  }

  return {
    tone: "default",
    label: accountId ?? "paper_account_001",
    hint: "控制动作、筛选条件与股票代码检查入口已集中展示。",
  };
}

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
  const activeMeta = VIEW_META[view];
  const activeSymbolLabel = formatSymbolLabel(selectedSymbol, symbolNames);
  const readiness = describeReadiness(dashboard.snapshot.status);
  const controlState = describeControlState(dashboard.snapshot.status);
  const focus = describeFocus(
    view,
    activeSymbolLabel,
    selectedMarketTimeframe,
    selectedResearchTimeframe,
    selectedResearchMode,
    dashboard.snapshot.status?.account_id,
  );
  const refreshDisabled =
    dashboard.isRefreshing
    || (view === "market" && marketData.isRefreshing)
    || (view === "research" && researchData.isRefreshing);
  const refreshLabel =
    dashboard.isRefreshing
    || (view === "market" && marketData.isRefreshing)
    || (view === "research" && researchData.isRefreshing)
      ? "更新中..."
      : "刷新数据";

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
      <div className="app-shell__glow app-shell__glow--left" />
      <div className="app-shell__glow app-shell__glow--right" />

      <div className="workspace-shell">
        <aside className="workspace-sidebar">
          <div className="workspace-brand">
            <p className="workspace-brand__eyebrow">SignalArk</p>
            <h1 className="workspace-brand__title">交易控制台</h1>
            <p className="workspace-brand__summary">
              统一展示导航、状态与关键操作入口，便于在单一界面完成监控、筛选与处置。
            </p>
          </div>

          <div className="workspace-sidebar__section">
            <p className="mini-label">主导航</p>
            <ViewSwitcher
              value={view}
              onChange={navigate}
            />
          </div>

          <div className="workspace-sidebar__section">
            <p className="mini-label">当前上下文</p>
            <div className="workspace-focus-card">
              <strong>{focus.label}</strong>
              <p>{focus.hint}</p>
            </div>
          </div>

          <div className="workspace-sidebar__section">
            <p className="mini-label">运行概况</p>
            <div className="workspace-sidebar__stack">
              <div className="workspace-sidebar__item">
                <span>账户</span>
                <strong>{dashboard.snapshot.status?.account_id ?? "paper_account_001"}</strong>
              </div>
              <div className="workspace-sidebar__item">
                <span>运行标的</span>
                <strong>{dashboard.snapshot.status?.symbols?.length ?? availableSymbols.length} 个</strong>
              </div>
              <div className="workspace-sidebar__item">
                <span>行情状态</span>
                <strong>{dashboard.snapshot.status?.market_data_fresh ? "最新" : "待确认"}</strong>
              </div>
            </div>
          </div>
        </aside>

        <main className="workspace-main">
          <header className="workspace-topbar">
            <div className="workspace-topbar__copy">
              <p className="workspace-topbar__eyebrow">{activeMeta.eyebrow}</p>
              <h2 className="workspace-topbar__title">{activeMeta.title}</h2>
              <p className="workspace-topbar__summary">{activeMeta.summary}</p>
            </div>

            <div className="workspace-topbar__actions">
              <div className="workspace-topbar__chips">
                <span className="workspace-chip">{titleCase(dashboard.snapshot.status?.execution_mode ?? "paper")}</span>
                <span className="workspace-chip">{titleCase(dashboard.snapshot.status?.health_status ?? "unknown")}</span>
                <span className="workspace-chip">{titleCase(dashboard.snapshot.status?.current_trading_phase ?? "unknown")}</span>
                {view !== "operations" ? <span className="workspace-chip">{activeSymbolLabel}</span> : null}
              </div>

              <div className="workspace-refresh-card">
                <span className="mini-label">最近更新</span>
                <strong>{formatDateTime(activeFetchedAt)}</strong>
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
            </div>
          </header>

          <section className="workspace-pulse">
            <article className={`workspace-pulse__card workspace-pulse__card--${readiness.tone}`}>
              <span className="mini-label">系统准备</span>
              <strong>{readiness.label}</strong>
              <p>{readiness.hint}</p>
            </article>
            <article className={`workspace-pulse__card workspace-pulse__card--${controlState.tone}`}>
              <span className="mini-label">控制状态</span>
              <strong>{controlState.label}</strong>
              <p>{controlState.hint}</p>
            </article>
            <article className={`workspace-pulse__card workspace-pulse__card--${focus.tone}`}>
              <span className="mini-label">页面焦点</span>
              <strong>{focus.label}</strong>
              <p>{focus.hint}</p>
            </article>
            <article className="workspace-pulse__card workspace-pulse__card--default">
              <span className="mini-label">当前持有实例</span>
              <strong>{dashboard.snapshot.status?.lease_owner_instance_id ?? "未确认"}</strong>
              <p>租约实例和最新数据时间固定展示在顶栏，减少来回切页核对。</p>
            </article>
          </section>

          <div className="workspace-stage">{renderView()}</div>
        </main>
      </div>
    </div>
  );
}
