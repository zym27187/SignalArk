import { buildTicks, resolveRange } from "../lib/chart";
import { formatDateTime, formatDecimal } from "../lib/format";
import type { CandleBar } from "../types/research";

interface CandlestickChartProps {
  title: string;
  subtitle: string;
  bars: CandleBar[];
}

export function CandlestickChart({ title, subtitle, bars }: CandlestickChartProps) {
  const width = 860;
  const height = 320;
  const margin = { top: 18, right: 16, bottom: 28, left: 10 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;

  const range = resolveRange(
    bars.flatMap((bar) => [bar.low, bar.high]),
    0.06,
    0.2,
  );
  const ticks = buildTicks(range, 5);
  const step = innerWidth / bars.length;
  const candleWidth = Math.max(6, Math.min(18, step * 0.56));

  const lastBar = bars[bars.length - 1];
  const firstBar = bars[0];
  const totalVolume = bars.reduce((sum, bar) => sum + bar.volume, 0);
  const sessionMove = lastBar.close - firstBar.open;
  const sessionMovePct = (sessionMove / firstBar.open) * 100;

  function scaleY(value: number) {
    return (
      margin.top +
      ((range.max - value) / Math.max(range.max - range.min, Number.EPSILON)) * innerHeight
    );
  }

  return (
    <div className="chart-shell">
      <div className="chart-shell__header">
        <div>
          <p className="mini-label">{title}</p>
          <h3 className="chart-shell__title">{subtitle}</h3>
        </div>
        <div className="chart-shell__summary">
          <strong>{formatDecimal(lastBar.close, 2)}</strong>
          <span>{`${sessionMove >= 0 ? "+" : ""}${formatDecimal(sessionMove, 2)} / ${sessionMovePct >= 0 ? "+" : ""}${formatDecimal(sessionMovePct, 2)}%`}</span>
        </div>
      </div>

      <div className="mini-metric-grid">
        <div className="mini-metric">
          <span className="mini-label">Session High</span>
          <strong>{formatDecimal(Math.max(...bars.map((bar) => bar.high)), 2)}</strong>
        </div>
        <div className="mini-metric">
          <span className="mini-label">Session Low</span>
          <strong>{formatDecimal(Math.min(...bars.map((bar) => bar.low)), 2)}</strong>
        </div>
        <div className="mini-metric">
          <span className="mini-label">Bars</span>
          <strong>{bars.length}</strong>
        </div>
        <div className="mini-metric">
          <span className="mini-label">Volume</span>
          <strong>{formatDecimal(totalVolume, 0)}</strong>
        </div>
      </div>

      <div className="chart">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="chart__svg"
          role="img"
          aria-label={`${title} candlestick chart`}
        >
          {ticks.map((tick) => {
            const y = scaleY(tick);
            return (
              <g key={tick}>
                <line
                  x1={margin.left}
                  x2={width - margin.right}
                  y1={y}
                  y2={y}
                  stroke="rgba(18, 40, 61, 0.08)"
                  strokeDasharray="4 6"
                />
                <text
                  x={width - margin.right}
                  y={y - 6}
                  textAnchor="end"
                  className="chart__tick-label"
                >
                  {formatDecimal(tick, 2)}
                </text>
              </g>
            );
          })}

          {bars.map((bar, index) => {
            const x = margin.left + index * step + step / 2;
            const openY = scaleY(bar.open);
            const closeY = scaleY(bar.close);
            const highY = scaleY(bar.high);
            const lowY = scaleY(bar.low);
            const bodyTop = Math.min(openY, closeY);
            const bodyHeight = Math.max(2, Math.abs(closeY - openY));
            const rising = bar.close >= bar.open;
            const fill = rising ? "#0c8f78" : "#b13f3f";

            return (
              <g key={bar.time}>
                <line
                  x1={x}
                  x2={x}
                  y1={highY}
                  y2={lowY}
                  stroke={fill}
                  strokeWidth="2"
                  strokeLinecap="round"
                />
                <rect
                  x={x - candleWidth / 2}
                  y={bodyTop}
                  width={candleWidth}
                  height={bodyHeight}
                  rx="4"
                  fill={fill}
                  opacity={rising ? 0.86 : 0.78}
                />
              </g>
            );
          })}
        </svg>
      </div>

      <div className="chart-shell__footer">
        <span>{formatDateTime(firstBar.time)}</span>
        <span>{formatDateTime(lastBar.time)}</span>
      </div>
    </div>
  );
}

