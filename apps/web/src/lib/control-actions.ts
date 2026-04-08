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
    description: "先停掉自动下单，但保留页面查看和人工处理能力。",
    tone: "default",
  },
  {
    key: "resumeStrategy",
    title: "恢复策略",
    description: "确认无误后，重新允许系统自动下单。",
    tone: "default",
  },
  {
    key: "enableKillSwitch",
    title: "开启熔断开关",
    description: "紧急暂停新的开仓，只保留减仓或清仓。",
    tone: "danger",
    requiresConfirmation: true,
    confirmationTitle: "确认开启熔断开关",
    confirmationDescription: "开启后会立即暂停新的开仓，只允许减仓或清仓继续执行。",
  },
  {
    key: "disableKillSwitch",
    title: "关闭熔断开关",
    description: "退出紧急暂停，恢复正常开仓通道。",
    tone: "default",
    requiresConfirmation: true,
    confirmationTitle: "确认关闭熔断开关",
    confirmationDescription: "关闭后会恢复开仓；如果风险保护仍在，它不会自动解除。",
  },
  {
    key: "cancelAll",
    title: "全部撤单",
    description: "撤掉当前还在排队的订单。",
    tone: "danger",
    requiresConfirmation: true,
    confirmationTitle: "确认执行全部撤单",
    confirmationDescription:
      "系统会逐笔处理当前未完成订单；处于保护状态时，部分仅减仓订单可能会被保留。",
  },
];

export function getControlActionDefinition(actionKey: ControlActionKey): ControlActionDefinition {
  const definition = CONTROL_ACTIONS.find((action) => action.key === actionKey);
  if (!definition) {
    throw new Error(`Unknown control action: ${actionKey}`);
  }

  return definition;
}
