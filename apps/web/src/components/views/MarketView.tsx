import { AreaChart } from "../AreaChart";
import { CandlestickChart } from "../CandlestickChart";
import { DatasetSwitcher } from "../DatasetSwitcher";
import { DefinitionGrid } from "../DefinitionGrid";
import { MetricCard } from "../MetricCard";
import { SectionCard } from "../SectionCard";
import type { MarketDataState } from "../../hooks/use-market-data";
import { formatDateTime, formatDecimal, titleCase } from "../../lib/format";
import { getResearchSnapshot } from "../../lib/research-fixtures";
import type { StatusPayload } from "../../types/api";

interface MarketViewProps {
  status: StatusPayload | null;
  marketData: MarketDataState;
  availableSymbols: string[];
  availableTimeframes: string[];
  selectedSymbol: string;
  selectedTimeframe: string;
  onSymbolChange: (symbol: string) => void;
  onTimeframeChange: (timeframe: string) => void;
}

function resolveSourceLabel(
  usingLiveBars: boolean,
  usingLiveCurve: boolean,
  fallbackLabel: string,
) {
  if (usingLiveBars && usingLiveCurve) {
    return "真实 API 数据";
  }

  if (usingLiveBars) {
    return "K 线真实 / 权益示例";
  }

  if (usingLiveCurve) {
    return "权益真实 / K 线示例";
  }

  return fallbackLabel;
}

export function MarketView({
  status,
  marketData,
  availableSymbols,
  availableTimeframes,
  selectedSymbol,
  selectedTimeframe,
  onSymbolChange,
  onTimeframeChange,
}: MarketViewProps) {
  const fallbackSnapshot = getResearchSnapshot(selectedSymbol, selectedTimeframe);
  const usingLiveBars = marketData.snapshot.bars.length > 0;
  const usingLiveCurve = marketData.snapshot.equityCurve.length > 0;
  const bars = usingLiveBars ? marketData.snapshot.bars : fallbackSnapshot.klineBars;
  const runtimePnlCurve = usingLiveCurve
    ? marketData.snapshot.equityCurve
    : fallbackSnapshot.runtimePnlCurve;
  const firstBar = bars[0];
  const lastBar = bars[bars.length - 1];
  const activeSymbol =
    marketData.snapshot.symbol ?? selectedSymbol ?? status?.symbols?.[0] ?? fallbackSnapshot.manifest.symbols[0];
  const timeframe = marketData.snapshot.timeframe ?? selectedTimeframe ?? fallbackSnapshot.manifest.timeframe;
  const sourceLabel = resolveSourceLabel(
    usingLiveBars,
    usingLiveCurve,
    fallbackSnapshot.sourceLabel,
  );
  const runtimeAudit = marketData.snapshot.runtimeBars;
  const runtimeSeenBar = runtimeAudit.last_seen_bars[0] ?? null;
  const runtimeStrategyBar = runtimeAudit.last_strategy_bars[0] ?? null;
  const sessionMove = lastBar.close - firstBar.open;
  const sessionMovePct = (sessionMove / firstBar.open) * 100;
  const maxEquity = Math.max(...runtimePnlCurve.map((point) => point.value));
  const minEquity = Math.min(...runtimePnlCurve.map((point) => point.value));
  const marketDataHint =
    marketData.snapshot.sectionErrors.bars ??
    marketData.snapshot.sectionErrors.equityCurve ??
    (usingLiveBars && usingLiveCurve
      ? "K 线和权益曲线都来自真实只读接口。"
      : "当只读接口返回空载荷或暂时不可用时，页面会自动回退到本地示例数据。");
  const runtimeAuditHint =
    marketData.snapshot.sectionErrors.runtimeBars ??
    (runtimeSeenBar
      ? "该审计视图展示 trader runtime 实际落盘的观察结果，不会重新回拉 Eastmoney 历史 K 线。"
      : runtimeAudit.available_streams.length > 0
        ? `当前 runtime 最近记录的流：${runtimeAudit.available_streams
            .map((stream) => `${stream.symbol}/${stream.timeframe}`)
            .join("、")}`
        : "当前 runtime 还没有落盘任何已观察或已消费的 bar。");

  return (
    <main className="page-stack">
      <section className="page-hero">
        <div className="page-hero__copy">
          <p className="page-hero__eyebrow">市场监控</p>
          <h2 className="page-hero__title">K 线区域与盘中盈亏骨架</h2>
          <p className="page-hero__summary">
            市场视图现在优先读取真实 K 线与账户权益接口；如果本地环境还没有累计足够
            的快照或只读接口暂时不可用，会自动回退到示例数据保持页面可用。
          </p>
          <DatasetSwitcher
            symbolOptions={availableSymbols.map((value) => ({ value }))}
            timeframeOptions={availableTimeframes.map((value) => ({ value }))}
            symbol={selectedSymbol}
            timeframe={selectedTimeframe}
            onSymbolChange={onSymbolChange}
            onTimeframeChange={onTimeframeChange}
          />
        </div>
        <div className="page-hero__chips">
          <span className={`tag${usingLiveBars && usingLiveCurve ? "" : " tag--fixture"}`}>
            {sourceLabel}
          </span>
          <span className="tag">{activeSymbol}</span>
          <span className="tag">{timeframe}</span>
        </div>
      </section>

      <section className="metric-grid metric-grid--three">
        <MetricCard
          label="最新价"
          value={formatDecimal(lastBar.close, 2)}
          hint={`收盘来源：${usingLiveBars ? "真实 K 线接口" : "示例数据"}`}
          tone="positive"
        />
        <MetricCard
          label="区间涨跌"
          value={`${sessionMove >= 0 ? "+" : ""}${formatDecimal(sessionMovePct, 2)}%`}
          hint={`${sessionMove >= 0 ? "+" : ""}${formatDecimal(sessionMove, 2)} 元`}
          tone={sessionMove >= 0 ? "positive" : "danger"}
        />
        <MetricCard
          label="区间权益带"
          value={`${formatDecimal(minEquity, 0)} - ${formatDecimal(maxEquity, 0)}`}
          hint={
            usingLiveCurve
              ? "基于余额快照、全账户成交与多标的价格重建"
              : "基于本地曲线示例数据推导"
          }
          tone="default"
        />
      </section>

      <section className="page-grid">
        <div className="page-grid__main">
          <SectionCard
            eyebrow="价格走势"
            title="K 线区域"
            description="针对选中标的和周期的真实蜡烛图视图。"
          >
            <CandlestickChart
              title={activeSymbol}
              subtitle={`${timeframe} K 线${usingLiveBars ? "" : "（示例兜底）"}`}
              bars={bars}
            />
          </SectionCard>

          <SectionCard
            eyebrow="盈亏"
            title="盘中权益曲线"
            description="按选中周期重建的整账户组合权益时间线。"
          >
            <AreaChart
              title="区间权益"
              subtitle={usingLiveCurve ? "组合权益重建曲线" : "以 100,000 模拟本金为基线"}
              points={runtimePnlCurve}
              accent="amber"
              formatAsMoney
            />
          </SectionCard>
        </div>

        <aside className="page-grid__rail">
          <SectionCard
            eyebrow="审计"
            title="Runtime 实际消费数据"
            description="补齐 trader 当时实际看到的 bar，而不只是临时重拉行情。"
          >
            <DefinitionGrid
              items={[
                {
                  label: "审计 API",
                  value: "/v1/market/runtime-bars",
                  hint: runtimeAuditHint,
                },
                {
                  label: "Last Seen Bar",
                  value: runtimeSeenBar
                    ? `${formatDateTime(runtimeSeenBar.event_time)} / ${formatDecimal(runtimeSeenBar.close, 2)}`
                    : "暂无匹配流",
                  hint: runtimeSeenBar
                    ? `${runtimeSeenBar.symbol} · ${runtimeSeenBar.timeframe} · ${runtimeSeenBar.source_kind ?? "unknown"}`
                    : `当前筛选 ${selectedSymbol} / ${selectedTimeframe} 还没有 runtime 落盘 bar。`,
                },
                {
                  label: "Last Strategy Bar",
                  value: runtimeStrategyBar
                    ? `${formatDateTime(runtimeStrategyBar.event_time)} / ${formatDecimal(runtimeStrategyBar.close, 2)}`
                    : "尚未进入策略",
                  hint: runtimeStrategyBar
                    ? `${runtimeStrategyBar.symbol} · ${runtimeStrategyBar.timeframe} · 真正送入策略的最新 bar`
                    : "如果当前流只被 runtime 看到、但还没真正送入策略，这里会保持为空。",
                },
                {
                  label: "已知流",
                  value:
                    runtimeAudit.available_streams.length > 0
                      ? runtimeAudit.available_streams
                          .map((stream) => `${stream.symbol}/${stream.timeframe}`)
                          .join(", ")
                      : "暂无",
                  hint: "这里展示 runtime 最近持有的 stream 视图，可快速判断页面筛选是否和 trader 实际消费流一致。",
                },
              ]}
            />
          </SectionCard>

          <SectionCard
            eyebrow="就绪度"
            title="数据面规划"
            description="市场页已切到真实 API，并保留开发态兜底。"
          >
            <DefinitionGrid
              items={[
                {
                  label: "当前来源",
                  value: sourceLabel,
                  hint: marketDataHint,
                },
                {
                  label: "K 线 API",
                  value: "/v1/market/bars",
                  hint:
                    marketData.snapshot.sectionErrors.bars ?? "查询参数：symbol + timeframe + limit。",
                },
                {
                  label: "权益 API",
                  value: "/v1/portfolio/equity-curve",
                  hint:
                    marketData.snapshot.sectionErrors.equityCurve ??
                    "使用余额快照、全账户成交与多标的历史价格重建组合权益曲线。",
                },
                {
                  label: "交易器状态",
                  value: titleCase(status?.control_state),
                  hint: "控制状态已经可以实时从 API 获取。",
                },
              ]}
            />
          </SectionCard>
        </aside>
      </section>
    </main>
  );
}
