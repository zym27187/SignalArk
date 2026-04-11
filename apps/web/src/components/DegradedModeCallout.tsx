import { titleCase } from "../lib/format";
import type { DegradedModeStatusPayload } from "../types/api";

interface DegradedModeCalloutProps {
  diagnostics: DegradedModeStatusPayload | null | undefined;
  title?: string;
  alwaysShow?: boolean;
}

export function DegradedModeCallout({
  diagnostics,
  title = "当前诊断状态",
  alwaysShow = false,
}: DegradedModeCalloutProps) {
  if (!diagnostics) {
    return null;
  }

  if (!alwaysShow && diagnostics.status === "normal") {
    return null;
  }

  return (
    <div className={`diagnostics-callout diagnostics-callout--${diagnostics.status}`}>
      <div className="diagnostics-callout__header">
        <div>
          <p className="mini-label">{title}</p>
          <strong>{diagnostics.message}</strong>
        </div>
        <div className="diagnostics-callout__badges">
          <span>{titleCase(diagnostics.status)}</span>
          <span>{titleCase(diagnostics.reason_code)}</span>
          <span>{titleCase(diagnostics.data_source)}</span>
        </div>
      </div>
      <p className="diagnostics-callout__impact">{diagnostics.impact}</p>
      <p className="diagnostics-callout__action">建议动作：{diagnostics.suggested_action}</p>
    </div>
  );
}
