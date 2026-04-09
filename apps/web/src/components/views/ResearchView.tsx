import { AreaChart } from "../AreaChart";
import { BacktestDecisionTable } from "../BacktestDecisionTable";
import { DatasetSwitcher } from "../DatasetSwitcher";
import { DefinitionGrid } from "../DefinitionGrid";
import { MetricCard } from "../MetricCard";
import { SectionCard } from "../SectionCard";
import type { ResearchDataState } from "../../hooks/use-research-data";
import {
  formatDateTime,
  formatDecimal,
  formatSignedMoney,
  formatSymbolLabel,
  formatSymbolList,
} from "../../lib/format";
import type { SymbolNameMap } from "../../types/api";

interface ResearchViewProps {
  researchData: ResearchDataState;
  availableSymbols: string[];
  symbolNames: SymbolNameMap;
  availableTimeframes: string[];
  selectedSymbol: string;
  selectedTimeframe: string;
  onSymbolChange: (symbol: string) => void;
  onTimeframeChange: (timeframe: string) => void;
}

export function ResearchView({
  researchData,
  availableSymbols,
  symbolNames,
  availableTimeframes,
  selectedSymbol,
  selectedTimeframe,
  onSymbolChange,
  onTimeframeChange,
}: ResearchViewProps) {
  const snapshot = researchData.snapshot;
  const manifest = snapshot?.manifest;
  const performance = snapshot?.performance;
  const equityCurve = snapshot?.equityCurve ?? [];
  const decisions = snapshot?.decisions ?? [];
  const notes = snapshot?.notes ?? [];
  const sourceLabel = snapshot
    ? snapshot.sourceMode === "fixture"
      ? snapshot.sourceLabel
      : "真实回测结果"
    : researchData.isLoading
      ? "正在生成回测结果"
      : "等待回测数据";
  const sourceIsFixture = snapshot?.sourceMode === "fixture";
  const metadataItems = manifest
    ? [
        {
          label: "本次回测编号",
          value: manifest.runId,
          hint: manifest.description,
        },
        {
          label: "回测时间范围",
          value: `${formatDateTime(manifest.startTime)} 至 ${formatDateTime(manifest.endTime)}`,
        },
        {
          label: "账户与标的",
          value: `${manifest.accountId} / ${formatSymbolList(manifest.symbols, symbolNames)}`,
          hint: `${manifest.handlerName} · ${manifest.timeframe}`,
        },
        {
          label: "交易成本假设",
          value: `滑点 ${formatDecimal(manifest.slippageBps, 0)} bps`,
          hint: `${manifest.feeModel} + ${manifest.slippageModel}`,
        },
        {
          label: "数据版本标识",
          value: manifest.dataFingerprint,
        },
        {
          label: "配置版本标识",
          value: manifest.manifestFingerprint,
        },
      ]
    : [
        {
          label: "当前状态",
          value: researchData.isLoading ? "生成中" : "等待数据",
          hint: researchData.error ?? "选择标的和周期后，这里会生成一份回测结果。",
        },
      ];

  return (
    <main className="page-stack">
      <section className="page-hero">
        <div className="page-hero__copy">
          <p className="page-hero__eyebrow">策略回看</p>
          <h2 className="page-hero__title">回测结果一眼看懂</h2>
          <p className="page-hero__summary">
            这里会按你选中的标的和周期，直接生成一份回测结果，帮助快速看清这套策略在这段时间里赚了多少、回撤多大、为什么买卖。
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
          <span className={`tag${sourceIsFixture ? " tag--fixture" : ""}`}>{sourceLabel}</span>
          <span className="tag">{formatSymbolLabel(selectedSymbol, symbolNames)}</span>
          <span className="tag">{manifest?.strategyId ?? "baseline_momentum_v1"}</span>
          <span className="tag">{manifest?.timeframe ?? selectedTimeframe}</span>
        </div>
      </section>

      <section className="metric-grid">
        <MetricCard
          label="这次赚亏"
          value={formatSignedMoney(performance?.netPnl)}
          hint={
            performance
              ? `收益率 ${formatDecimal(performance.totalReturnPct, 4)}%`
              : "等待回测结果。"
          }
          tone={performance && performance.netPnl >= 0 ? "positive" : "default"}
        />
        <MetricCard
          label="中途最大回落"
          value={
            performance
              ? `${formatDecimal(performance.maxDrawdownPct, 4)}%`
              : "--"
          }
          hint={performance ? "回测过程中从高点回落最多的一次" : "等待回测结果。"}
          tone="warning"
        />
        <MetricCard
          label="完成交易数"
          value={performance?.tradeCount ?? "--"}
          hint={
            performance
              ? `${performance.fillCount} 笔成交 / ${performance.signalCount} 个信号`
              : "等待回测结果。"
          }
          tone="default"
        />
        <MetricCard
          label="结束时账户资金"
          value={formatDecimal(performance?.endingEquity, 2)}
          hint={
            performance
              ? `期初 ${formatDecimal(performance.startingEquity, 2)}`
              : "等待回测结果。"
          }
          tone="default"
        />
      </section>

      <section className="page-grid">
        <div className="page-grid__main">
          <SectionCard
            eyebrow="资金变化"
            title="账户资金变化"
            description="看选中标的在这次回测里的账户资金变化。"
          >
            {researchData.error ? <p className="section-error">{researchData.error}</p> : null}
            {equityCurve.length > 0 && manifest ? (
              <AreaChart
                title="回测资金"
                subtitle={`${formatSymbolList(manifest.symbols, symbolNames)} · ${manifest.timeframe} · ${manifest.barCount} 根 K 线`}
                points={equityCurve}
                accent="red"
                formatAsMoney
              />
            ) : (
              <div className="empty-state">
                <p className="empty-state__title">
                  {researchData.isLoading ? "正在生成回测结果" : "暂无回测结果"}
                </p>
                <p className="empty-state__copy">
                  {researchData.error
                    ? "当前请求失败，可稍后重试或手动刷新。"
                    : "切换到这里后，页面会基于真实历史价格即时生成一份回测结果。"}
                </p>
              </div>
            )}
          </SectionCard>

          <SectionCard
            eyebrow="买卖原因"
            title="每一步为什么买卖"
            description="按时间列出信号、动作和下单计划。"
          >
            {decisions.length > 0 ? (
              <BacktestDecisionTable decisions={decisions} />
            ) : (
              <div className="empty-state">
                <p className="empty-state__title">还没有决策记录</p>
                <p className="empty-state__copy">
                  生成回测结果后，这里会展示每一步的信号和下单计划。
                </p>
              </div>
            )}
          </SectionCard>
        </div>

        <aside className="page-grid__rail">
          <SectionCard
            eyebrow="回测信息"
            title="本次回放信息"
            description="这次回测用的时间范围、标的和成本假设。"
          >
            <DefinitionGrid items={metadataItems} />
          </SectionCard>

          <SectionCard
            eyebrow="数据说明"
            title="这页数据从哪来"
            description="说明当前展示的数据来源和接入方式。"
          >
            {notes.length > 0 ? (
              <ul className="note-list">
                {notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            ) : (
              <div className="empty-state">
                <p className="empty-state__title">等待说明内容</p>
                <p className="empty-state__copy">
                  回测结果返回后，这里会展示当前回放来源和页面说明。
                </p>
              </div>
            )}
          </SectionCard>
        </aside>
      </section>
    </main>
  );
}
