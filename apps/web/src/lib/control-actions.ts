import type { ControlActionKey } from "./api";

export interface ControlActionDefinition {
  key: ControlActionKey;
  title: string;
  description: string;
  tone: "default" | "danger";
  requiresConfirmation?: boolean;
  confirmationTitle?: string;
  confirmationDescription?: string;
}

export const CONTROL_ACTIONS: ControlActionDefinition[] = [
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
    requiresConfirmation: true,
    confirmationTitle: "确认开启熔断开关",
    confirmationDescription: "开启后将阻断新的开仓动作，只允许减仓或清仓方向执行。",
  },
  {
    key: "disableKillSwitch",
    title: "关闭熔断开关",
    description: "退出人工应急模式，同时不改变现有保护状态。",
    tone: "default",
    requiresConfirmation: true,
    confirmationTitle: "确认关闭熔断开关",
    confirmationDescription: "关闭熔断后会恢复开仓通道；若保护模式仍生效，其状态不会自动解除。",
  },
  {
    key: "cancelAll",
    title: "全部撤单",
    description: "请求撤销控制平面内所有符合条件的活动订单。",
    tone: "danger",
    requiresConfirmation: true,
    confirmationTitle: "确认执行全部撤单",
    confirmationDescription:
      "系统会逐笔处理当前活动订单；在熔断或保护模式下，保护性 reduce-only 订单可能被跳过。",
  },
];

export function getControlActionDefinition(actionKey: ControlActionKey): ControlActionDefinition {
  const definition = CONTROL_ACTIONS.find((action) => action.key === actionKey);
  if (!definition) {
    throw new Error(`Unknown control action: ${actionKey}`);
  }

  return definition;
}
