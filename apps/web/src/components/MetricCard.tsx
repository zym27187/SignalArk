import type { ReactNode } from "react";

interface MetricCardProps {
  label: string;
  value: ReactNode;
  hint: string;
  tone?: "default" | "positive" | "warning" | "danger";
}

export function MetricCard({
  label,
  value,
  hint,
  tone = "default",
}: MetricCardProps) {
  return (
    <article className={`metric-card metric-card--${tone}`}>
      <p className="metric-card__label">{label}</p>
      <strong className="metric-card__value">{value}</strong>
      <p className="metric-card__hint">{hint}</p>
    </article>
  );
}

