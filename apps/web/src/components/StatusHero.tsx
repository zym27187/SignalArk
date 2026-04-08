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
  const summary = status
    ? `当前${titleCase(status.control_state)}，系统${titleCase(status.lifecycle_status)}，${
        status.ready ? "可以继续运行" : "暂时等待中"
      }。${status.strategy_enabled ? "自动策略已开启。" : "自动策略已暂停。"}`
    : "连上数据服务后，这里会显示系统是否在线、能不能运行，以及最近行情有没有更新。";

  return (
    <section className={`status-hero status-hero--${tone}`}>
      <div className="status-hero__copy">
        <p className="status-hero__eyebrow">交易总览</p>
        <h1 className="status-hero__title">
          {isLoading ? "正在整理最新状态..." : "交易运行总览"}
        </h1>
        <p className="status-hero__summary">{summary}</p>
        {error ? <p className="status-hero__error">状态读取失败：{error}</p> : null}
      </div>

      <div className="status-hero__meta-grid">
        <div className="status-chip">
          <span className="status-chip__label">当前环境</span>
          <strong>{titleCase(status?.env ?? "dev")}</strong>
        </div>
        <div className="status-chip">
          <span className="status-chip__label">交易模式</span>
          <strong>{titleCase(status?.execution_mode ?? "paper")}</strong>
        </div>
        <div className="status-chip">
          <span className="status-chip__label">当前实例</span>
          <strong>{compactId(status?.lease_owner_instance_id)}</strong>
        </div>
        <div className="status-chip">
          <span className="status-chip__label">最近行情时间</span>
          <strong>{formatDateTime(status?.latest_final_bar_time)}</strong>
        </div>
      </div>
    </section>
  );
}
