import { API_BASE_URL, type ControlActionKey } from "../lib/api";
import { formatDateTime, titleCase } from "../lib/format";
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
    title: "Pause Strategy",
    description: "Stop new strategy-triggered actions while keeping runtime visibility.",
    tone: "default",
  },
  {
    key: "resumeStrategy",
    title: "Resume Strategy",
    description: "Re-enable strategy-triggered submissions after operator review.",
    tone: "default",
  },
  {
    key: "enableKillSwitch",
    title: "Enable Kill Switch",
    description: "Block new opening flow and keep only reducing actions available.",
    tone: "danger",
  },
  {
    key: "disableKillSwitch",
    title: "Disable Kill Switch",
    description: "Return from manual emergency mode without changing protection state.",
    tone: "default",
  },
  {
    key: "cancelAll",
    title: "Cancel All Orders",
    description: "Request cancellation of every eligible active order in the control plane.",
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
          <span className="mini-label">Current Control State</span>
          <strong>{titleCase(status?.control_state)}</strong>
        </div>
        <div>
          <span className="mini-label">Last Cancel-All</span>
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
                {busy ? "Working..." : action.title}
              </span>
              <span className="control-button__description">{action.description}</span>
            </button>
          );
        })}
      </div>

      <div className="control-panel__footer">
        <p className="control-panel__message">
          {actionMessage ?? "Operator actions will post to the live FastAPI control plane."}
        </p>
        <p className="control-panel__endpoint">API target: {API_BASE_URL}</p>
      </div>
    </div>
  );
}

