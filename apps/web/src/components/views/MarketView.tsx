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
          <p className="page-hero__eyebrow">市场监控</p>
          <h2 className="page-hero__title">K 线区域与盘中盈亏骨架</h2>
          <p className="page-hero__summary">
            这个视图按未来实时市场监控页的结构搭建。在 K 线 API 就绪前，先使用本地
            示例数据模拟相同的标的与周期语义。
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
          label="最新价"
          value={formatDecimal(lastBar.close, 2)}
          hint={`收盘来源：${status?.market_data_fresh ? "实时" : "示例数据"}`}
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
          hint="基于本地曲线示例数据推导"
          tone="default"
        />
      </section>

      <section className="page-grid">
        <div className="page-grid__main">
          <SectionCard
            eyebrow="价格走势"
            title="K 线区域"
            description="针对单个跟踪标的和单条活跃周期的蜡烛图骨架。"
          >
            <CandlestickChart
              title={activeSymbol}
              subtitle="15m K 线，预留后续实时叠加层"
              bars={bars}
            />
          </SectionCard>

          <SectionCard
            eyebrow="盈亏"
            title="盘中权益曲线"
            description="为未来实时持仓时间线预留的运行时盈亏面积图占位。"
          >
            <AreaChart
              title="区间权益"
              subtitle="以 100,000 模拟本金为基线"
              points={runtimePnlCurve}
              accent="amber"
              formatAsMoney
            />
          </SectionCard>
        </div>

        <aside className="page-grid__rail">
          <SectionCard
            eyebrow="就绪度"
            title="数据面规划"
            description="在行情历史 API 落地前，视觉结构已经可以先行验证。"
          >
            <DefinitionGrid
              items={[
                {
                  label: "当前来源",
                  value: "本地示例数据",
                  hint: "来自前端强类型示例数据，而非 HTTP K 线接口。",
                },
                {
                  label: "未来 K 线 API",
                  value: "/v1/market/bars",
                  hint: "可能的查询参数：symbol + timeframe + limit。",
                },
                {
                  label: "未来权益 API",
                  value: "/v1/portfolio/equity-curve",
                  hint: "可支持实时盯市权益历史。",
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
