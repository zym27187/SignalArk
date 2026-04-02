import { AreaChart } from "../AreaChart";
import { CandlestickChart } from "../CandlestickChart";
import { DefinitionGrid } from "../DefinitionGrid";
import { MetricCard } from "../MetricCard";
import { SectionCard } from "../SectionCard";
import { formatDecimal, titleCase } from "../../lib/format";
import { researchSnapshotFixture } from "../../lib/research-fixtures";
import type { StatusPayload } from "../../types/api";

interface MarketViewProps {
  status: StatusPayload | null;
}

export function MarketView({ status }: MarketViewProps) {
  const bars = researchSnapshotFixture.klineBars;
  const runtimePnlCurve = researchSnapshotFixture.runtimePnlCurve;
  const firstBar = bars[0];
  const lastBar = bars[bars.length - 1];
  const activeSymbol = status?.symbols?.[0] ?? researchSnapshotFixture.manifest.symbols[0];
  const sessionMove = lastBar.close - firstBar.open;
  const sessionMovePct = (sessionMove / firstBar.open) * 100;
  const maxEquity = Math.max(...runtimePnlCurve.map((point) => point.value));
  const minEquity = Math.min(...runtimePnlCurve.map((point) => point.value));

  return (
    <main className="page-stack">
      <section className="page-hero">
        <div className="page-hero__copy">
          <p className="page-hero__eyebrow">Market Monitor</p>
          <h2 className="page-hero__title">K-line region and intraday PnL skeleton</h2>
          <p className="page-hero__summary">
            This view is intentionally shaped like the future live market monitor. Until a bars API
            exists, it renders a local fixture with the same symbol and timeframe semantics.
          </p>
        </div>
        <div className="page-hero__chips">
          <span className="tag tag--fixture">{researchSnapshotFixture.sourceLabel}</span>
          <span className="tag">{activeSymbol}</span>
          <span className="tag">{researchSnapshotFixture.manifest.timeframe}</span>
        </div>
      </section>

      <section className="metric-grid metric-grid--three">
        <MetricCard
          label="Last Price"
          value={formatDecimal(lastBar.close, 2)}
          hint={`Close ${status?.market_data_fresh ? "fresh" : "fixture"}`}
          tone="positive"
        />
        <MetricCard
          label="Session Move"
          value={`${sessionMove >= 0 ? "+" : ""}${formatDecimal(sessionMovePct, 2)}%`}
          hint={`${sessionMove >= 0 ? "+" : ""}${formatDecimal(sessionMove, 2)} CNY`}
          tone={sessionMove >= 0 ? "positive" : "danger"}
        />
        <MetricCard
          label="Session Equity Band"
          value={`${formatDecimal(minEquity, 0)} - ${formatDecimal(maxEquity, 0)}`}
          hint="Derived from local curve fixture"
          tone="default"
        />
      </section>

      <section className="page-grid">
        <div className="page-grid__main">
          <SectionCard
            eyebrow="Price Action"
            title="K-line Region"
            description="Candlestick scaffold for one tracked symbol and one active timeframe."
          >
            <CandlestickChart
              title={activeSymbol}
              subtitle="15m bars with room for future live overlays"
              bars={bars}
            />
          </SectionCard>

          <SectionCard
            eyebrow="PnL"
            title="Intraday Equity Curve"
            description="Runtime PnL area chart placeholder for a future live positions timeline."
          >
            <AreaChart
              title="Session Equity"
              subtitle="From baseline 100,000 paper capital"
              points={runtimePnlCurve}
              accent="amber"
              formatAsMoney
            />
          </SectionCard>
        </div>

        <aside className="page-grid__rail">
          <SectionCard
            eyebrow="Readiness"
            title="Data Surface Plan"
            description="The visual structure is ready before the market-history APIs land."
          >
            <DefinitionGrid
              items={[
                {
                  label: "Current Source",
                  value: "Local fixture",
                  hint: "Rendered from typed frontend fixtures, not HTTP bars.",
                },
                {
                  label: "Future Bars API",
                  value: "/v1/market/bars",
                  hint: "Likely query: symbol + timeframe + limit.",
                },
                {
                  label: "Future PnL API",
                  value: "/v1/portfolio/equity-curve",
                  hint: "Would support live mark-to-market history.",
                },
                {
                  label: "Trader State",
                  value: titleCase(status?.control_state),
                  hint: "Real-time control state already comes from the API.",
                },
              ]}
            />
          </SectionCard>
        </aside>
      </section>
    </main>
  );
}
