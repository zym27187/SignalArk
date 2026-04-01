import { compactId, formatDateTime, titleCase } from "../lib/format";
import type { StatusPayload } from "../types/api";

interface StatusHeroProps {
  status: StatusPayload | null;
  isLoading: boolean;
  error?: string;
}

function statusTone(
  ready: boolean | undefined,
  controlState: string | undefined,
): "positive" | "warning" | "danger" {
  if (controlState === "kill_switch" || controlState === "protection_mode") {
    return "danger";
  }

  if (ready) {
    return "positive";
  }

  return "warning";
}

export function StatusHero({ status, isLoading, error }: StatusHeroProps) {
  const tone = statusTone(status?.ready, status?.control_state);

  return (
    <section className={`status-hero status-hero--${tone}`}>
      <div className="status-hero__copy">
        <p className="status-hero__eyebrow">SignalArk Operator Console</p>
        <h1 className="status-hero__title">
          {isLoading ? "Preparing runtime snapshot..." : "Paper trading control surface"}
        </h1>
        <p className="status-hero__summary">
          {status
            ? `${titleCase(status.control_state)} · ${titleCase(status.lifecycle_status)} · ${
                status.ready ? "Ready" : "Standby"
              }`
            : "Connect the frontend to the API and confirm the trader runtime is publishing status."}
        </p>
        {error ? <p className="status-hero__error">Status feed issue: {error}</p> : null}
      </div>

      <div className="status-hero__meta-grid">
        <div className="status-chip">
          <span className="status-chip__label">Env</span>
          <strong>{status?.env ?? "dev"}</strong>
        </div>
        <div className="status-chip">
          <span className="status-chip__label">Mode</span>
          <strong>{status?.execution_mode ?? "paper"}</strong>
        </div>
        <div className="status-chip">
          <span className="status-chip__label">Lease Owner</span>
          <strong>{compactId(status?.lease_owner_instance_id)}</strong>
        </div>
        <div className="status-chip">
          <span className="status-chip__label">Latest Bar</span>
          <strong>{formatDateTime(status?.latest_final_bar_time)}</strong>
        </div>
      </div>
    </section>
  );
}

