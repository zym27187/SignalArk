import { AreaChart } from "../AreaChart";
import { CandlestickChart } from "../CandlestickChart";
import { DatasetSwitcher } from "../DatasetSwitcher";
import { DefinitionGrid } from "../DefinitionGrid";
import { MetricCard } from "../MetricCard";
import { SectionCard } from "../SectionCard";
import type { MarketDataState } from "../../hooks/use-market-data";
import {
  formatDateTime,
  formatDecimal,
  formatSymbolLabel,
  titleCase,
} from "../../lib/format";
import { getResearchSnapshot } from "../../lib/research-fixtures";
import type { StatusPayload, SymbolNameMap } from "../../types/api";

interface MarketViewProps {
  status: StatusPayload | null;
  marketData: MarketDataState;
  availableSymbols: string[];
  symbolNames: SymbolNameMap;
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
    return "真实数据";
  }

  if (usingLiveBars) {
    return "价格真实 / 资金示例";
  }

  if (usingLiveCurve) {
    return "资金真实 / 价格示例";
  }

  return fallbackLabel;
}

export function MarketView({
  status,
  marketData,
  availableSymbols,
  symbolNames,
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
  const displayedEquityCurve = usingLiveCurve
    ? marketData.snapshot.equityCurve
    : fallbackSnapshot.equityCurve;
  const firstBar = bars[0];
  const lastBar = bars[bars.length - 1];
  const activeSymbol =
    marketData.snapshot.symbol ?? selectedSymbol ?? status?.symbols?.[0] ?? fallbackSnapshot.manifest.symbols[0];
  const activeSymbolLabel = formatSymbolLabel(activeSymbol, symbolNames);
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
  const maxEquity = Math.max(...displayedEquityCurve.map((point) => point.value));
  const minEquity = Math.min(...displayedEquityCurve.map((point) => point.value));
  const marketDataHint =
    marketData.snapshot.sectionErrors.bars ??
    marketData.snapshot.sectionErrors.equityCurve ??
    (usingLiveBars && usingLiveCurve
      ? "价格和账户曲线都来自实时接口。"
      : "如果实时接口暂时没返回数据，页面会自动切换到本地示例数据。");
  const runtimeAuditHint =
    marketData.snapshot.sectionErrors.runtimeBars ??
    (runtimeSeenBar
      ? "这里展示的是交易系统当时实际记录到的价格。"
      : runtimeAudit.available_streams.length > 0
        ? `系统最近记录的品种：${runtimeAudit.available_streams
            .map((stream) => `${formatSymbolLabel(stream.symbol, symbolNames)}/${stream.timeframe}`)
            .join("、")}`
        : "系统暂时还没有记录到对应的价格。");

  return (
    <main className="page-stack">
      <section className="page-hero">
        <div className="page-hero__copy">
          <p className="page-hero__eyebrow">市场走势</p>
          <h2 className="page-hero__title">价格走势与账户盈亏</h2>
          <p className="page-hero__summary">
            这里优先展示真实价格和账户曲线；如果本地还没积累足够数据，页面会自动用示例数据补位，保证图表始终可看。
          </p>
          <DatasetSwitcher
            symbolOptions={availableSymbols.map((value) => ({
              value,
              label: formatSymbolLabel(value, symbolNames),
            }))}
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
          <span className="tag">{activeSymbolLabel}</span>
          <span className="tag">{timeframe}</span>
        </div>
      </section>

      <section className="metric-grid metric-grid--three">
        <MetricCard
          label="最新价"
          value={formatDecimal(lastBar.close, 2)}
          hint={`价格来源：${usingLiveBars ? "真实价格接口" : "示例数据"}`}
          tone="positive"
        />
        <MetricCard
          label="这段时间涨跌"
          value={`${sessionMove >= 0 ? "+" : ""}${formatDecimal(sessionMovePct, 2)}%`}
          hint={`累计变化 ${sessionMove >= 0 ? "+" : ""}${formatDecimal(sessionMove, 2)} 元`}
          tone={sessionMove >= 0 ? "positive" : "danger"}
        />
        <MetricCard
          label="账户资金范围"
          value={`${formatDecimal(minEquity, 0)} - ${formatDecimal(maxEquity, 0)}`}
          hint={
            usingLiveCurve
              ? "按账户余额、成交和价格变化重建"
              : "基于本地示例数据估算"
          }
          tone="default"
        />
      </section>

      <section className="page-grid">
        <div className="page-grid__main">
          <SectionCard
            eyebrow="价格走势"
            title="价格变化"
            description="看选中标的在这段时间里的价格变化。"
          >
            <CandlestickChart
              title={activeSymbolLabel}
              subtitle={`${timeframe} 价格走势${usingLiveBars ? "" : "（示例补位）"}`}
              bars={bars}
            />
          </SectionCard>

          <SectionCard
            eyebrow="账户变化"
            title="账户盈亏变化"
            description="看这段时间账户资金是怎么波动的。"
          >
            <AreaChart
              title="账户资金"
              subtitle={usingLiveCurve ? "按真实账户变化重建" : "以 100,000 模拟本金为基线"}
              points={displayedEquityCurve}
              accent="amber"
              formatAsMoney
            />
          </SectionCard>
        </div>

        <aside className="page-grid__rail">
          <SectionCard
            eyebrow="核对"
            title="系统实际看到的数据"
            description="确认交易系统当时看到的最新行情，而不是事后重新拉取的数据。"
          >
            <DefinitionGrid
              items={[
                {
                  label: "查看接口",
                  value: "/v1/market/runtime-bars",
                  hint: runtimeAuditHint,
                },
                {
                  label: "系统最近看到",
                  value: runtimeSeenBar
                    ? `${formatDateTime(runtimeSeenBar.event_time)} / ${formatDecimal(runtimeSeenBar.close, 2)}`
                    : "暂无匹配流",
                  hint: runtimeSeenBar
                    ? `${formatSymbolLabel(runtimeSeenBar.symbol, symbolNames)} · ${runtimeSeenBar.timeframe} · ${runtimeSeenBar.source_kind ?? "unknown"}`
                    : `当前筛选 ${formatSymbolLabel(selectedSymbol, symbolNames)} / ${selectedTimeframe} 还没有落盘记录。`,
                },
                {
                  label: "最近用于决策",
                  value: runtimeStrategyBar
                    ? `${formatDateTime(runtimeStrategyBar.event_time)} / ${formatDecimal(runtimeStrategyBar.close, 2)}`
                    : "还没进入策略",
                  hint: runtimeStrategyBar
                    ? `${formatSymbolLabel(runtimeStrategyBar.symbol, symbolNames)} · ${runtimeStrategyBar.timeframe} · 真正送入策略的最新价格`
                    : "如果系统看到了价格，但还没真正拿去做策略判断，这里会保持为空。",
                },
                {
                  label: "已记录品种",
                  value:
                    runtimeAudit.available_streams.length > 0
                      ? runtimeAudit.available_streams
                          .map(
                            (stream) =>
                              `${formatSymbolLabel(stream.symbol, symbolNames)}/${stream.timeframe}`,
                          )
                          .join(", ")
                      : "暂无",
                  hint: "这里展示系统最近记录过的品种和周期，可快速判断页面筛选是否和真实消费流一致。",
                },
              ]}
            />
          </SectionCard>

          <SectionCard
            eyebrow="数据说明"
            title="当前数据接入情况"
            description="说明页面现在用的是真实数据还是示例数据。"
          >
            <DefinitionGrid
              items={[
                {
                  label: "当前展示数据",
                  value: sourceLabel,
                  hint: marketDataHint,
                },
                {
                  label: "价格接口",
                  value: "/v1/market/bars",
                  hint:
                    marketData.snapshot.sectionErrors.bars ?? "按标的、周期和条数读取价格。",
                },
                {
                  label: "账户曲线接口",
                  value: "/v1/portfolio/equity-curve",
                  hint:
                    marketData.snapshot.sectionErrors.equityCurve ??
                    "使用账户余额、成交和价格变化重建资金曲线。",
                },
                {
                  label: "系统控制状态",
                  value: titleCase(status?.control_state),
                  hint: "当前交易状态已经可以实时从接口获取。",
                },
              ]}
            />
          </SectionCard>
        </aside>
      </section>
    </main>
  );
}
