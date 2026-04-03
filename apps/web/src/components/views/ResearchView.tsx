import { AreaChart } from "../AreaChart";
import { BacktestDecisionTable } from "../BacktestDecisionTable";
import { DatasetSwitcher } from "../DatasetSwitcher";
import { DefinitionGrid } from "../DefinitionGrid";
import { MetricCard } from "../MetricCard";
import { SectionCard } from "../SectionCard";
import type { ResearchDataState } from "../../hooks/use-research-data";
import { formatDateTime, formatDecimal, formatSignedMoney } from "../../lib/format";

interface ResearchViewProps {
  researchData: ResearchDataState;
  availableSymbols: string[];
  availableTimeframes: string[];
  selectedSymbol: string;
  selectedTimeframe: string;
  onSymbolChange: (symbol: string) => void;
  onTimeframeChange: (timeframe: string) => void;
}

export function ResearchView({
  researchData,
  availableSymbols,
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
  const sourceLabel = snapshot?.sourceLabel
    ?? (researchData.isLoading ? "正在生成真实回测快照" : "等待 research 数据");
  const sourceIsFixture = snapshot?.sourceMode === "fixture";
  const metadataItems = manifest
    ? [
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
      ]
    : [
        {
          label: "当前状态",
          value: researchData.isLoading ? "生成中" : "等待数据",
          hint: researchData.error ?? "选择 symbol/timeframe 后会调用 /v1/research/snapshot。",
        },
      ];

  return (
    <main className="page-stack">
      <section className="page-hero">
        <div className="page-hero__copy">
          <p className="page-hero__eyebrow">研究实验室</p>
          <h2 className="page-hero__title">真实回测结果页</h2>
          <p className="page-hero__summary">
            当前研究页会直接请求 `/v1/research/snapshot`，按选中的 symbol/timeframe
            生成一份真实 backtest snapshot，并统一展示 research 回测权益曲线。
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
          <span className={`tag${sourceIsFixture ? " tag--fixture" : ""}`}>{sourceLabel}</span>
          <span className="tag">{manifest?.strategyId ?? "baseline_momentum_v1"}</span>
          <span className="tag">{manifest?.timeframe ?? selectedTimeframe}</span>
        </div>
      </section>

      <section className="metric-grid">
        <MetricCard
          label="净收益"
          value={formatSignedMoney(performance?.netPnl)}
          hint={
            performance
              ? `收益率 ${formatDecimal(performance.totalReturnPct, 4)}%`
              : "等待回测结果。"
          }
          tone={performance && performance.netPnl >= 0 ? "positive" : "default"}
        />
        <MetricCard
          label="最大回撤"
          value={
            performance
              ? `${formatDecimal(performance.maxDrawdownPct, 4)}%`
              : "--"
          }
          hint={performance ? "整段回放过程中的峰谷回撤" : "等待回测结果。"}
          tone="warning"
        />
        <MetricCard
          label="交易次数"
          value={performance?.tradeCount ?? "--"}
          hint={
            performance
              ? `${performance.fillCount} 笔成交 / ${performance.signalCount} 个信号`
              : "等待回测结果。"
          }
          tone="default"
        />
        <MetricCard
          label="期末权益"
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
            eyebrow="绩效"
            title="权益曲线"
            description="当前按 symbol/timeframe 选择展示的 research 回测权益曲线。"
          >
            {researchData.error ? <p className="section-error">{researchData.error}</p> : null}
            {equityCurve.length > 0 && manifest ? (
              <AreaChart
                title="回测权益"
                subtitle={`${manifest.symbols.join(", ")} · ${manifest.timeframe} · ${manifest.barCount} 根 K 线`}
                points={equityCurve}
                accent="red"
                formatAsMoney
              />
            ) : (
              <div className="empty-state">
                <p className="empty-state__title">
                  {researchData.isLoading ? "正在生成 research 快照" : "暂无 research 快照"}
                </p>
                <p className="empty-state__copy">
                  {researchData.error
                    ? "当前请求失败，可稍后重试或手动刷新。"
                    : "切换到研究视图后，页面会基于真实历史 K 线即时生成回测结果。"}
                </p>
              </div>
            )}
          </SectionCard>

          <SectionCard
            eyebrow="审计"
            title="决策时间线"
            description="与回测决策记录模型对齐的逐 Bar 信号与订单计划审计。"
          >
            {decisions.length > 0 ? (
              <BacktestDecisionTable decisions={decisions} />
            ) : (
              <div className="empty-state">
                <p className="empty-state__title">尚无决策记录</p>
                <p className="empty-state__copy">
                  生成研究快照后，这里会展示逐 bar 的信号与订单计划审计。
                </p>
              </div>
            )}
          </SectionCard>
        </div>

        <aside className="page-grid__rail">
          <SectionCard
            eyebrow="清单"
            title="运行元数据"
            description="可序列化的运行标识与回放假设。"
          >
            <DefinitionGrid items={metadataItems} />
          </SectionCard>

          <SectionCard
            eyebrow="说明"
            title="前端集成说明"
            description="当前数据来源、入口契约，以及研究页的实时接线方式。"
          >
            {notes.length > 0 ? (
              <ul className="note-list">
                {notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            ) : (
              <div className="empty-state">
                <p className="empty-state__title">等待说明数据</p>
                <p className="empty-state__copy">
                  research 快照返回后，这里会展示当前回放来源和前端集成说明。
                </p>
              </div>
            )}
          </SectionCard>
        </aside>
      </section>
    </main>
  );
}
