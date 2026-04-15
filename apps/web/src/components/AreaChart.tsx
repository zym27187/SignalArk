import { buildAreaPath, buildLinePath, buildTicks, resolveRange } from "../lib/chart";
import { formatDateTime, formatDecimal, formatMoney, formatSignedMoney } from "../lib/format";
import type { CurvePoint } from "../types/research";

interface AreaChartProps {
  title: string;
  subtitle: string;
  points: CurvePoint[];
  accent?: "teal" | "amber" | "red";
  formatAsMoney?: boolean;
}

const chartPalette = {
  teal: {
    line: "#0c8f78",
    fill: "rgba(12, 143, 120, 0.22)",
  },
  amber: {
    line: "#b35c23",
    fill: "rgba(179, 92, 35, 0.22)",
  },
  red: {
    line: "#b13f3f",
    fill: "rgba(177, 63, 63, 0.18)",
  },
} as const;

export function AreaChart({
  title,
  subtitle,
  points,
  accent = "teal",
  formatAsMoney = false,
}: AreaChartProps) {
  const width = 860;
  const height = 280;
  const margin = { top: 20, right: 18, bottom: 30, left: 18 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const palette = chartPalette[accent];

  const values = points.map((point) => point.value);
  const range = resolveRange(values, 0.1, 5);
  const ticks = buildTicks(range);

  const cartesianPoints = points.map((point, index) => {
    const x = margin.left + (index / Math.max(points.length - 1, 1)) * innerWidth;
    const y =
      margin.top + ((range.max - point.value) / Math.max(range.max - range.min, 1)) * innerHeight;
    return { x, y };
  });

  const areaPath = buildAreaPath(cartesianPoints, margin.top + innerHeight);
  const linePath = buildLinePath(cartesianPoints);
  const firstPoint = points[0];
  const lastPoint = points[points.length - 1];
  const delta = lastPoint.value - firstPoint.value;
  const valueFormatter = formatAsMoney ? formatMoney : formatDecimal;
  const deltaFormatter = formatAsMoney ? formatSignedMoney : formatDecimal;

  return (
    <div className="chart-shell">
      <div className="chart-shell__header">
        <div>
          <p className="mini-label">{title}</p>
          <h3 className="chart-shell__title">{subtitle}</h3>
        </div>
        <div className="chart-shell__summary">
          <strong>{valueFormatter(lastPoint.value)}</strong>
          <span>
            {formatAsMoney ? `净变化 ${deltaFormatter(delta)}` : `变化 ${deltaFormatter(delta)}`}
          </span>
        </div>
      </div>

      <div className="chart">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="chart__svg"
          role="img"
          aria-label={`${title}图表`}
        >
          {ticks.map((tick) => {
            const y =
              margin.top + ((range.max - tick) / Math.max(range.max - range.min, 1)) * innerHeight;
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
                  {valueFormatter(tick)}
                </text>
              </g>
            );
          })}

          <path
            d={areaPath}
            fill={palette.fill}
          />
          <path
            d={linePath}
            fill="none"
            stroke={palette.line}
            strokeWidth="3"
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {cartesianPoints.map((point, index) => (
            <circle
              key={`${points[index].time}-${points[index].value}`}
              cx={point.x}
              cy={point.y}
              r={index === cartesianPoints.length - 1 ? 4.5 : 3}
              fill={palette.line}
            />
          ))}
        </svg>
      </div>

      <div className="chart-shell__footer">
        <span>{formatDateTime(firstPoint.time)}</span>
        <span>{formatDateTime(lastPoint.time)}</span>
      </div>
    </div>
  );
}
