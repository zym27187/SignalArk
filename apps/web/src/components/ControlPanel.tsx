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
          <span className="mini-label">当前控制状态</span>
          <strong>{titleCase(status?.control_state)}</strong>
        </div>
        <div>
          <span className="mini-label">最近一次全撤</span>
          <strong>{formatDateTime(status?.last_cancel_all_at)}</strong>
        </div>
      </div>

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
          <div className="control-panel__confirmation-actions">
            <button
              type="button"
              className="control-button control-button--danger"
              onClick={confirmAction}
              disabled={pendingAction !== null}
            >
              <span className="control-button__title">确认执行</span>
              <span className="control-button__description">
                该动作会立即提交到当前在线控制平面。
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
            ? "高风险动作需要二次确认，避免误触直接影响线上控制状态。"
            : "操作动作将提交到在线 FastAPI 控制平面。"}
        </p>
        <p className="control-panel__endpoint">API 目标：{API_BASE_URL}</p>
      </div>
    </div>
  );
}
