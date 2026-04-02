import { AreaChart } from "../AreaChart";
import { BacktestDecisionTable } from "../BacktestDecisionTable";
import { DatasetSwitcher } from "../DatasetSwitcher";
import { DefinitionGrid } from "../DefinitionGrid";
import { MetricCard } from "../MetricCard";
import { SectionCard } from "../SectionCard";
import { formatDateTime, formatDecimal, formatSignedMoney } from "../../lib/format";
import { getResearchSnapshot } from "../../lib/research-fixtures";

interface ResearchViewProps {
  availableSymbols: string[];
  availableTimeframes: string[];
  selectedSymbol: string;
  selectedTimeframe: string;
  onSymbolChange: (symbol: string) => void;
  onTimeframeChange: (timeframe: string) => void;
}

export function ResearchView({
  availableSymbols,
  availableTimeframes,
  selectedSymbol,
  selectedTimeframe,
  onSymbolChange,
  onTimeframeChange,
}: ResearchViewProps) {
  const snapshot = getResearchSnapshot(selectedSymbol, selectedTimeframe);
  const { manifest, performance, backtestEquityCurve, decisions, notes } = snapshot;

  return (
    <main className="page-stack">
      <section className="page-hero">
        <div className="page-hero__copy">
          <p className="page-hero__eyebrow">研究实验室</p>
          <h2 className="page-hero__title">回测结果页骨架</h2>
          <p className="page-hero__summary">
            本页对应 `BacktestRunResult` 的结构：运行清单、绩效摘要、权益曲线，以及
            逐根 K 线驱动的决策审计。
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
          <span className="tag tag--fixture">{snapshot.sourceLabel}</span>
          <span className="tag">{manifest.strategyId}</span>
          <span className="tag">{manifest.timeframe}</span>
        </div>
      </section>

      <section className="metric-grid">
        <MetricCard
          label="净收益"
          value={formatSignedMoney(performance.netPnl)}
          hint={`收益率 ${formatDecimal(performance.totalReturnPct, 4)}%`}
          tone={performance.netPnl >= 0 ? "positive" : "danger"}
        />
        <MetricCard
          label="最大回撤"
          value={`${formatDecimal(performance.maxDrawdownPct, 4)}%`}
          hint="整段回放过程中的峰谷回撤"
          tone="warning"
        />
        <MetricCard
          label="交易次数"
          value={performance.tradeCount}
          hint={`${performance.fillCount} 笔成交 / ${performance.signalCount} 个信号`}
          tone="default"
        />
        <MetricCard
          label="期末权益"
          value={formatDecimal(performance.endingEquity, 2)}
          hint={`期初 ${formatDecimal(performance.startingEquity, 2)}`}
          tone="default"
        />
      </section>

      <section className="page-grid">
        <div className="page-grid__main">
          <SectionCard
            eyebrow="绩效"
            title="权益曲线"
            description="当前按 symbol/timeframe 选择展示的研究回测权益曲线。"
          >
            <AreaChart
              title="回测权益"
              subtitle={`${manifest.symbols.join(", ")} · ${manifest.timeframe} · ${manifest.barCount} 根 K 线`}
              points={backtestEquityCurve}
              accent="red"
              formatAsMoney
            />
          </SectionCard>

          <SectionCard
            eyebrow="审计"
            title="决策时间线"
            description="与回测决策记录模型对齐的逐 Bar 信号与订单计划审计。"
          >
            <BacktestDecisionTable decisions={decisions} />
          </SectionCard>
        </div>

        <aside className="page-grid__rail">
          <SectionCard
            eyebrow="清单"
            title="运行元数据"
            description="可序列化的运行标识与回放假设。"
          >
            <DefinitionGrid
              items={[
                {
                  label: "运行 ID",
                  value: manifest.runId,
                  hint: manifest.description,
                },
                {
                  label: "时间窗口",
                  value: `${formatDateTime(manifest.startTime)} 至 ${formatDateTime(manifest.endTime)}`,
                },
                {
                  label: "账户 / 标的",
                  value: `${manifest.accountId} / ${manifest.symbols.join(", ")}`,
                  hint: `${manifest.handlerName} · ${manifest.timeframe}`,
                },
                {
                  label: "成本假设",
                  value: `滑点 ${formatDecimal(manifest.slippageBps, 0)} bps`,
                  hint: `${manifest.feeModel} + ${manifest.slippageModel}`,
                },
                {
                  label: "数据指纹",
                  value: manifest.dataFingerprint,
                },
                {
                  label: "清单指纹",
                  value: manifest.manifestFingerprint,
                },
              ]}
            />
          </SectionCard>

          <SectionCard
            eyebrow="说明"
            title="前端集成说明"
            description="当前切换能力、CLI 入口，以及后续待接入的研究数据源。"
          >
            <ul className="note-list">
              {notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </SectionCard>
        </aside>
      </section>
    </main>
  );
}
