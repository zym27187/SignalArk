import { compactId, formatDateTime, titleCase } from "../lib/format";
import type { StatusPayload } from "../types/api";
import { DegradedModeCallout } from "./DegradedModeCallout";

interface StatusHeroProps {
  status: StatusPayload | null;
  isLoading: boolean;
  error?: string;
}

function formatAuditProvider(providerId: string | null | undefined): string {
  switch (providerId) {
    case "openai_chat_completions":
      return "OpenAI Chat Completions";
    case "heuristic_stub":
      return "Heuristic Stub";
    case "deterministic_policy":
      return "Deterministic Policy";
    default:
      return titleCase(providerId ?? "--");
  }
}

function statusTone(
  ready: boolean | undefined,
  controlState: string | undefined,
  degradedStatus: string | undefined,
): "positive" | "warning" | "danger" {
  if (controlState === "kill_switch" || controlState === "protection_mode") {
    return "danger";
  }

  if (
    degradedStatus === "degraded"
    || degradedStatus === "missing"
    || degradedStatus === "fixture"
  ) {
    return "warning";
  }

  if (ready) {
    return "positive";
  }

  return "warning";
}

function buildStatusSummary(status: StatusPayload | null): { summary: string; impact: string } {
  if (!status) {
    return {
      summary: "系统状态还没接通。连上数据服务后，这里会先告诉你系统能不能继续工作。",
      impact: "当前影响：在状态恢复前，不要默认自动策略仍在正常运行。",
    };
  }

  if (status.degraded_mode && status.degraded_mode.status !== "normal") {
    return {
      summary: "系统当前存在明确的诊断降级，下面会直接说明原因、影响和建议动作。",
      impact: `当前影响：${status.degraded_mode.impact}`,
    };
  }

  if (status.control_state === "kill_switch" || status.control_state === "protection_mode") {
    return {
      summary:
        "系统当前处于紧急保护状态。自动策略虽然仍处于开启状态，但新的开仓动作会被拦住。",
      impact:
        "当前影响：你仍然可以查看状态、处理撤单和减仓，但不能把系统当成正常自动交易中。",
    };
  }

  if (!status.market_data_fresh) {
    return {
      summary: "系统状态已连通，但最近行情可能不是最新，自动判断需要更谨慎地看待。",
      impact: "当前影响：页面还能看历史状态，但不应把它当成最新盘中价格依据。",
    };
  }

  if (!status.ready) {
    return {
      summary: "系统已经启动，但还没达到可放心运行的状态。",
      impact: "当前影响：现在更适合先排查 readiness，而不是继续依赖自动策略。",
    };
  }

  return {
    summary: "系统当前运行正常。自动策略已开启，页面读取到的状态也保持连通。",
    impact: "当前影响：可以继续观察持仓、订单和事件时间线，并把这里当成主控制台。",
  };
}

export function StatusHero({ status, isLoading, error }: StatusHeroProps) {
  const tone = statusTone(
    status?.ready,
    status?.control_state,
    status?.degraded_mode?.status,
  );
  const { summary, impact } = buildStatusSummary(status);

  return (
    <section className={`status-hero status-hero--${tone}`}>
      <div className="status-hero__copy">
        <p className="status-hero__eyebrow">交易总览</p>
        <h1 className="status-hero__title">
          {isLoading ? "正在整理最新状态..." : "交易运行总览"}
        </h1>
        <p className="status-hero__summary">{summary}</p>
        <p className="status-hero__impact">{impact}</p>
        <DegradedModeCallout diagnostics={status?.degraded_mode} title="诊断结论" />
        {status?.last_strategy_audit ? (
          <div className="status-hero__decision">
            <p className="status-hero__decision-eyebrow">最近一次策略判断</p>
            <strong>{`${titleCase(status.last_strategy_audit.decision ?? "hold")} · ${formatAuditProvider(status.last_strategy_audit.provider_id)}`}</strong>
            <p>{status.last_strategy_audit.reason_summary ?? "当前还没有可解释的策略摘要。"}</p>
            <p>{`策略：${status.last_strategy_id ?? "--"} · 决策时间：${formatDateTime(status.last_strategy_decision_at)}`}</p>
            {status.last_strategy_audit.confidence ? (
              <p>{`置信度：${status.last_strategy_audit.confidence}`}</p>
            ) : null}
            {status.last_strategy_audit.fallback_used ? (
              <p>{`已降级到 deterministic fallback：${status.last_strategy_audit.fallback_reason ?? "外部 provider 暂不可用"}`}</p>
            ) : null}
          </div>
        ) : null}
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
