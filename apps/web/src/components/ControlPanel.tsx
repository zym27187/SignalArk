import { useState } from "react";

import { API_BASE_URL, type ControlActionKey } from "../lib/api";
import {
  CONTROL_ACTIONS,
  getControlActionDefinition,
  type ControlActionDefinition,
} from "../lib/control-actions";
import { formatDateTime, titleCase } from "../lib/format";
import type { DashboardControlActionResult, StatusPayload } from "../types/api";

interface ControlPanelProps {
  status: StatusPayload | null;
  pendingAction: ControlActionKey | null;
  lastActionResult: DashboardControlActionResult | null;
  onAction: (actionKey: ControlActionKey) => void | Promise<void>;
}

function hasOrderStats(result: DashboardControlActionResult | null): boolean {
  if (!result) {
    return false;
  }

  return (
    result.requestedOrderCount !== null ||
    result.cancelledOrderCount !== null ||
    result.skippedOrderCount !== null
  );
}

function describeCurrentControlImpact(status: StatusPayload | null): string {
  if (!status) {
    return "状态尚未加载完成前，不要默认系统还在正常自动交易。";
  }
  if (status.control_state === "kill_switch") {
    return "当前已经处于紧急刹车状态，新的开仓不会继续放行。";
  }
  if (status.control_state === "protection_mode") {
    return "当前正在风险保护中，系统会更保守地限制动作。";
  }
  return "当前控制状态正常，人工动作会直接影响在线控制服务。";
}

function describeConfirmationImpact(action: ControlActionDefinition): string {
  if (action.key === "enableKillSwitch") {
    return "开启后，系统会阻止新的开仓，只保留减仓或清仓相关动作。";
  }
  if (action.key === "disableKillSwitch") {
    return "关闭后会恢复开仓通道，但不会自动解除其他风险保护。";
  }
  if (action.key === "cancelAll") {
    return "系统会尝试撤掉当前排队订单，但保护性减仓订单可能会被保留。";
  }
  return "该操作会立即作用到当前在线控制服务。";
}

function describeResultImpact(result: DashboardControlActionResult | null): string | null {
  if (!result || !result.accepted) {
    return null;
  }
  if (result.actionKey === "cancelAll") {
    return "这意味着系统已经开始撤销当前排队订单，但保护性减仓单可能继续保留。";
  }
  if (result.actionKey === "enableKillSwitch") {
    return "这意味着新的开仓已经被拦住，后续只会保留更保守的处理动作。";
  }
  if (result.actionKey === "pauseStrategy") {
    return "这意味着系统不会继续自动下新单，但你仍然可以查看状态和人工处理。";
  }
  return "这次动作已经写入控制面，后续状态刷新会继续反映实际结果。";
}

export function ControlPanel({
  status,
  pendingAction,
  lastActionResult,
  onAction,
}: ControlPanelProps) {
  const [confirmingActionKey, setConfirmingActionKey] = useState<ControlActionKey | null>(null);
  const confirmingAction: ControlActionDefinition | null = confirmingActionKey
    ? getControlActionDefinition(confirmingActionKey)
    : null;

  function handleActionClick(action: ControlActionDefinition) {
    if (action.requiresConfirmation) {
      setConfirmingActionKey(action.key);
      return;
    }

    setConfirmingActionKey(null);
    void onAction(action.key);
  }

  function confirmAction() {
    if (!confirmingActionKey) {
      return;
    }

    const actionKey = confirmingActionKey;
    setConfirmingActionKey(null);
    void onAction(actionKey);
  }

  return (
    <div className="control-panel">
      <div className="control-panel__status-strip">
        <div>
          <span className="mini-label">系统当前状态</span>
          <strong>{titleCase(status?.control_state)}</strong>
        </div>
        <div>
          <span className="mini-label">上次全部撤单</span>
          <strong>{formatDateTime(status?.last_cancel_all_at)}</strong>
        </div>
      </div>
      <p className="control-panel__state-help">{describeCurrentControlImpact(status)}</p>

      <div className="control-panel__actions">
        {CONTROL_ACTIONS.map((action) => {
          const busy = pendingAction === action.key;

          return (
            <button
              key={action.key}
              type="button"
              className={`control-button control-button--${action.tone}`}
              onClick={() => {
                handleActionClick(action);
              }}
              disabled={pendingAction !== null}
            >
              <span className="control-button__title">{busy ? "处理中..." : action.title}</span>
              <span className="control-button__description">{action.description}</span>
              {action.requiresConfirmation ? (
                <span className="control-button__hint">高风险动作，执行前需确认</span>
              ) : null}
            </button>
          );
        })}
      </div>

      {confirmingAction ? (
        <div className="control-panel__confirmation" role="alert">
          <span className="mini-label">危险动作确认</span>
          <strong>{confirmingAction.confirmationTitle}</strong>
          <p>{confirmingAction.confirmationDescription}</p>
          <p className="control-panel__impact">{describeConfirmationImpact(confirmingAction)}</p>
          <div className="control-panel__confirmation-actions">
            <button
              type="button"
              className="control-button control-button--danger"
              onClick={confirmAction}
              disabled={pendingAction !== null}
            >
              <span className="control-button__title">确认执行</span>
              <span className="control-button__description">
                该操作会立即发送到当前在线控制服务。
              </span>
            </button>
            <button
              type="button"
              className="control-button"
              onClick={() => {
                setConfirmingActionKey(null);
              }}
              disabled={pendingAction !== null}
            >
              <span className="control-button__title">取消</span>
              <span className="control-button__description">返回控制动作列表，不提交本次操作。</span>
            </button>
          </div>
        </div>
      ) : null}

      {lastActionResult ? (
        <div
          className={`control-panel__result ${
            lastActionResult.accepted
              ? "control-panel__result--accepted"
              : "control-panel__result--failed"
          }`}
        >
          <div className="control-panel__result-header">
            <div>
              <span className="mini-label">最近一次动作</span>
              <strong>{lastActionResult.actionLabel}</strong>
            </div>
            <div>
              <span className="mini-label">动作结果</span>
              <strong>{lastActionResult.accepted ? "已落地" : "执行失败"}</strong>
            </div>
          </div>
          <p className="control-panel__message">{lastActionResult.message}</p>
          {describeResultImpact(lastActionResult) ? (
            <p className="control-panel__impact">{describeResultImpact(lastActionResult)}</p>
          ) : null}
          {hasOrderStats(lastActionResult) ? (
            <div className="control-panel__result-stats">
              <div>
                <span className="mini-label">请求数</span>
                <strong>{lastActionResult.requestedOrderCount ?? 0}</strong>
              </div>
              <div>
                <span className="mini-label">成功撤单</span>
                <strong>{lastActionResult.cancelledOrderCount ?? 0}</strong>
              </div>
              <div>
                <span className="mini-label">跳过数</span>
                <strong>{lastActionResult.skippedOrderCount ?? 0}</strong>
              </div>
            </div>
          ) : null}
          <div className="control-panel__result-meta">
            <span>控制状态：{titleCase(lastActionResult.controlState)}</span>
            <span>
              {lastActionResult.effectiveAt ? "生效时间" : "记录时间"}：
              {formatDateTime(lastActionResult.effectiveAt ?? lastActionResult.requestedAt)}
            </span>
          </div>
        </div>
      ) : null}

      <div className="control-panel__footer">
        <p className="control-panel__message">
          {confirmingAction
            ? "高风险操作需要二次确认，避免误触直接影响当前交易状态。"
            : "这里的操作会直接发送到在线控制服务。"}
        </p>
        <p className="control-panel__endpoint">当前接口：{API_BASE_URL}</p>
      </div>
    </div>
  );
}
