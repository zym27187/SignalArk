import { API_BASE_URL, type ControlActionKey } from "../lib/api";
import { formatDateTime, localizeMessage, titleCase } from "../lib/format";
import type { StatusPayload } from "../types/api";

interface ControlPanelProps {
  status: StatusPayload | null;
  pendingAction: ControlActionKey | null;
  actionMessage: string | null;
  onAction: (actionKey: ControlActionKey) => void | Promise<void>;
}

const controlActions: Array<{
  key: ControlActionKey;
  title: string;
  description: string;
  tone: "default" | "danger";
}> = [
  {
    key: "pauseStrategy",
    title: "暂停策略",
    description: "停止新的策略触发动作，同时保留运行时可见性。",
    tone: "default",
  },
  {
    key: "resumeStrategy",
    title: "恢复策略",
    description: "在人工复核后重新允许策略触发提交流程。",
    tone: "default",
  },
  {
    key: "enableKillSwitch",
    title: "开启熔断开关",
    description: "阻断新的开仓流程，仅保留减仓或清仓动作。",
    tone: "danger",
  },
  {
    key: "disableKillSwitch",
    title: "关闭熔断开关",
    description: "退出人工应急模式，同时不改变现有保护状态。",
    tone: "default",
  },
  {
    key: "cancelAll",
    title: "全部撤单",
    description: "请求撤销控制平面内所有符合条件的活动订单。",
    tone: "danger",
  },
];

export function ControlPanel({
  status,
  pendingAction,
  actionMessage,
  onAction,
}: ControlPanelProps) {
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
        {controlActions.map((action) => {
          const busy = pendingAction === action.key;

          return (
            <button
              key={action.key}
              type="button"
              className={`control-button control-button--${action.tone}`}
              onClick={() => {
                void onAction(action.key);
              }}
              disabled={pendingAction !== null}
            >
              <span className="control-button__title">
                {busy ? "处理中..." : action.title}
              </span>
              <span className="control-button__description">{action.description}</span>
            </button>
          );
        })}
      </div>

      <div className="control-panel__footer">
        <p className="control-panel__message">
          {localizeMessage(actionMessage) || "操作动作将提交到在线 FastAPI 控制平面。"}
        </p>
        <p className="control-panel__endpoint">API 目标：{API_BASE_URL}</p>
      </div>
    </div>
  );
}
