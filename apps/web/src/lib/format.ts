const DISPLAY_VALUE_MAP: Record<string, string> = {
  account_scope: "账户范围",
  ack: "已接收",
  accepted: "已接受",
  acquired: "已获取",
  active: "活跃",
  alive: "正常",
  allow: "通过",
  auction: "竞价",
  booting: "引导中",
  bound: "已绑定",
  buy: "买入",
  call_auction: "集合竞价",
  canceled: "已撤单",
  cancelled: "已撤单",
  close_auction: "收盘集合竞价",
  closed: "收盘",
  continuous_auction: "连续竞价",
  continuous_trading: "连续竞价",
  created: "已创建",
  degraded: "降级",
  dev: "开发环境",
  draining: "排空中",
  entry: "开仓",
  execution: "执行",
  expired: "已失效",
  exit: "平仓",
  filled: "已成交",
  fresh: "最新",
  healthy: "健康",
  initializing: "初始化中",
  kill_switch: "已紧急暂停",
  limit: "限价",
  live: "实盘交易",
  lost: "已丢失",
  maker: "挂单成交",
  market: "市价",
  midday_break: "午间休市",
  new: "待处理",
  none: "无",
  normal: "正常运行",
  not_ready: "未就绪",
  open: "开盘",
  open_auction: "开盘集合竞价",
  observed: "已观察",
  paper: "模拟交易",
  partially_filled: "部分成交",
  paused: "已暂停",
  pending: "待处理",
  position: "持仓",
  pre_open: "盘前",
  production: "生产环境",
  protection_mode: "风险保护中",
  ready: "已就绪",
  rebalance: "再平衡",
  rejected: "已拒绝",
  replay: "回放",
  reserved: "已保留",
  running: "运行中",
  sell: "卖出",
  sellable_qty_exhausted: "可卖数量不足",
  signal: "信号",
  skip: "跳过",
  staging: "预发",
  stale: "过期",
  starting: "启动中",
  stopped: "已停止",
  stopping: "停止中",
  strategy_paused: "已手动暂停",
  submitted: "已提交",
  suspended: "停牌",
  taker: "主动成交",
  unbound: "未绑定",
  unhealthy: "异常",
  unknown: "未知",
};

const DISPLAY_MESSAGE_MAP: Record<string, string> = {
  "Cancel-all request applied to active orders.": "全撤请求已应用到当前活动订单。",
  "Kill switch disabled; protection mode, if active, is unchanged.":
    "熔断开关已关闭；若保护模式当前生效，其状态保持不变。",
  "Kill switch enabled; only reducing or flattening actions remain allowed.":
    "熔断开关已开启；当前仅允许减仓或清仓动作。",
  "Request failed.": "请求失败。",
  "Strategy paused.": "策略已暂停。",
  "Strategy resumed.": "策略已恢复。",
};

function normalizeSymbol(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  const normalized = value.trim().toUpperCase();
  return normalized || null;
}

export function compactId(value: string | null | undefined): string {
  if (!value) {
    return "不可用";
  }

  if (value.length <= 12) {
    return value;
  }

  return `${value.slice(0, 8)}...${value.slice(-4)}`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "不可用";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(parsed);
}

export function formatDecimal(
  value: string | number | null | undefined,
  fractionDigits = 2,
): string {
  if (value === null || value === undefined || value === "") {
    return "--";
  }

  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }

  return new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(numeric);
}

export function formatSignedMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "--";
  }

  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }

  const sign = numeric > 0 ? "+" : "";
  return `${sign}${formatDecimal(numeric, 2)}`;
}

export function formatSymbolLabel(
  symbol: string | null | undefined,
  symbolNames?: Record<string, string> | null,
  fallbackLabel = "未知标的",
): string {
  const normalized = normalizeSymbol(symbol);
  if (!normalized) {
    return fallbackLabel;
  }

  const displayName = symbolNames?.[normalized];
  return displayName ? `${displayName} (${normalized})` : normalized;
}

export function formatSymbolList(
  symbols: string[] | null | undefined,
  symbolNames?: Record<string, string> | null,
): string {
  if (!symbols || symbols.length === 0) {
    return "暂无标的";
  }

  return symbols.map((symbol) => formatSymbolLabel(symbol, symbolNames)).join(", ");
}

export function summarizePayload(payload: Record<string, unknown> | null | undefined): string {
  if (!payload || Object.keys(payload).length === 0) {
    return "无载荷详情";
  }

  const serialized = JSON.stringify(payload);
  if (serialized.length <= 132) {
    return serialized;
  }

  return `${serialized.slice(0, 129)}...`;
}

export function titleCase(value: string | null | undefined): string {
  if (!value) {
    return "未知";
  }

  const normalized = value.trim().replace(/[\s-]+/g, "_").toLowerCase();
  if (DISPLAY_VALUE_MAP[normalized]) {
    return DISPLAY_VALUE_MAP[normalized];
  }

  return normalized
    .split("_")
    .filter(Boolean)
    .map(
      (segment) =>
        DISPLAY_VALUE_MAP[segment] ??
        segment.charAt(0).toUpperCase() + segment.slice(1).toLowerCase(),
    )
    .join(" ");
}

export function localizeMessage(message: string | null | undefined): string {
  if (!message) {
    return "";
  }

  if (DISPLAY_MESSAGE_MAP[message]) {
    return DISPLAY_MESSAGE_MAP[message];
  }

  const requestFailedMatch = message.match(/^Request failed with status (\d+)\.$/);
  if (requestFailedMatch) {
    return `请求失败，状态码 ${requestFailedMatch[1]}。`;
  }

  return message;
}
