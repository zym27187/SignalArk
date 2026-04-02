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
        <p className="status-hero__eyebrow">SignalArk 运维控制台</p>
        <h1 className="status-hero__title">
          {isLoading ? "正在准备运行时快照..." : "模拟交易控制面板"}
        </h1>
        <p className="status-hero__summary">
          {status
            ? `${titleCase(status.control_state)} · ${titleCase(status.lifecycle_status)} · ${
                status.ready ? "就绪" : "待命"
              }`
            : "前端接入 API 后，即可确认交易运行时是否正在持续发布状态。"}
        </p>
        {error ? <p className="status-hero__error">状态流异常：{error}</p> : null}
      </div>

      <div className="status-hero__meta-grid">
        <div className="status-chip">
          <span className="status-chip__label">环境</span>
          <strong>{titleCase(status?.env ?? "dev")}</strong>
        </div>
        <div className="status-chip">
          <span className="status-chip__label">模式</span>
          <strong>{titleCase(status?.execution_mode ?? "paper")}</strong>
        </div>
        <div className="status-chip">
          <span className="status-chip__label">租约持有者</span>
          <strong>{compactId(status?.lease_owner_instance_id)}</strong>
        </div>
        <div className="status-chip">
          <span className="status-chip__label">最新 K 线</span>
          <strong>{formatDateTime(status?.latest_final_bar_time)}</strong>
        </div>
      </div>
    </section>
  );
}
