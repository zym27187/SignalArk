import { AreaChart } from "../AreaChart";
import { BacktestDecisionTable } from "../BacktestDecisionTable";
import { DefinitionGrid } from "../DefinitionGrid";
import { MetricCard } from "../MetricCard";
import { SectionCard } from "../SectionCard";
import { formatDateTime, formatDecimal, formatSignedMoney } from "../../lib/format";
import { researchSnapshotFixture } from "../../lib/research-fixtures";

export function ResearchView() {
  const { manifest, performance, backtestEquityCurve, decisions, notes } = researchSnapshotFixture;

  return (
    <main className="page-stack">
      <section className="page-hero">
        <div className="page-hero__copy">
          <p className="page-hero__eyebrow">Research Lab</p>
          <h2 className="page-hero__title">Backtest results page skeleton</h2>
          <p className="page-hero__summary">
            This page mirrors the structure of `BacktestRunResult`: run manifest, performance
            summary, equity curve, and bar-driven decision audit.
          </p>
        </div>
        <div className="page-hero__chips">
          <span className="tag tag--fixture">{researchSnapshotFixture.sourceLabel}</span>
          <span className="tag">{manifest.strategyId}</span>
          <span className="tag">{manifest.timeframe}</span>
        </div>
      </section>

      <section className="metric-grid">
        <MetricCard
          label="Net PnL"
          value={formatSignedMoney(performance.netPnl)}
          hint={`Return ${formatDecimal(performance.totalReturnPct, 4)}%`}
          tone={performance.netPnl >= 0 ? "positive" : "danger"}
        />
        <MetricCard
          label="Max Drawdown"
          value={`${formatDecimal(performance.maxDrawdownPct, 4)}%`}
          hint="Peak-to-trough drawdown over the replay"
          tone="warning"
        />
        <MetricCard
          label="Trades"
          value={performance.tradeCount}
          hint={`${performance.fillCount} fills / ${performance.signalCount} signals`}
          tone="default"
        />
        <MetricCard
          label="Ending Equity"
          value={formatDecimal(performance.endingEquity, 2)}
          hint={`Starting ${formatDecimal(performance.startingEquity, 2)}`}
          tone="default"
        />
      </section>

      <section className="page-grid">
        <div className="page-grid__main">
          <SectionCard
            eyebrow="Performance"
            title="Equity Curve"
            description="Area chart prepared for a future research API that returns end-of-bar equity points."
          >
            <AreaChart
              title="Backtest Equity"
              subtitle={`${manifest.symbols.join(", ")} · ${manifest.timeframe} · ${manifest.barCount} bars`}
              points={backtestEquityCurve}
              accent="red"
              formatAsMoney
            />
          </SectionCard>

          <SectionCard
            eyebrow="Audit"
            title="Decision Timeline"
            description="Bar-level signal and order-plan audit aligned to the backtest decision record model."
          >
            <BacktestDecisionTable decisions={decisions} />
          </SectionCard>
        </div>

        <aside className="page-grid__rail">
          <SectionCard
            eyebrow="Manifest"
            title="Run Metadata"
            description="Serializable run identity and replay assumptions."
          >
            <DefinitionGrid
              items={[
                {
                  label: "Run ID",
                  value: manifest.runId,
                  hint: manifest.description,
                },
                {
                  label: "Time Window",
                  value: `${formatDateTime(manifest.startTime)} -> ${formatDateTime(manifest.endTime)}`,
                },
                {
                  label: "Account / Symbols",
                  value: `${manifest.accountId} / ${manifest.symbols.join(", ")}`,
                  hint: `${manifest.handlerName} on ${manifest.timeframe}`,
                },
                {
                  label: "Cost Assumptions",
                  value: `${formatDecimal(manifest.slippageBps, 0)} bps slippage`,
                  hint: `${manifest.feeModel} + ${manifest.slippageModel}`,
                },
                {
                  label: "Dataset Fingerprint",
                  value: manifest.dataFingerprint,
                },
                {
                  label: "Manifest Fingerprint",
                  value: manifest.manifestFingerprint,
                },
              ]}
            />
          </SectionCard>

          <SectionCard
            eyebrow="Notes"
            title="Frontend Integration Notes"
            description="What is real today, and what this page is waiting for next."
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
