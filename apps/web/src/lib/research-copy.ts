import type {
  BacktestDecisionSnapshot,
  BacktestManifestSnapshot,
} from "../types/research";
import { formatDecimal, localizeMessage, titleCase } from "./format";

const STRATEGY_DESCRIPTION_MAP: Record<string, string> = {
  "Long-only threshold momentum against previous close.":
    "只做多的阈值动量策略，主要根据收盘价相对前收的强弱变化来决定是否入场、加仓或离场。",
  "LLM-ready bar judgment strategy with a safe heuristic fallback.":
    "基于大模型的 K 线判断策略，会先让模型评估最近一组 K 线；如果外部模型不可用，再回退到本地启发式策略继续回测。",
};

const DIRECT_REASON_MAP: Record<string, string> = {
  "provider timed out": "模型服务响应超时",
  "market regime is mixed": "当前市场方向信号分化，先保持观望。",
  "too uncertain": "当前判断把握不足，先不执行交易。",
  "bullish bar stack": "最近一组 K 线呈现偏多结构。",
  "bearish reversal": "出现偏空反转信号。",
  "uptrend confirmed": "上涨趋势已经确认。",
  "fallback heuristic confirmed the move": "回退启发式策略确认了这次方向判断。",
  "model confirmed the bullish stack": "模型确认最近一组 K 线偏多，因此执行买入。",
  "saved config triggered the entry": "已保存的模型配置触发了这次入场。",
  "heuristic_stub judged the bar stack bullish enough to target the configured inventory.":
    "启发式回退策略判断最近一组 K 线足够偏多，因此把仓位调到设定目标。",
  "heuristic_stub judged downside momentum strong enough to flatten.":
    "启发式回退策略判断下行动能已经足够强，因此执行清仓。",
  "heuristic_stub judged the current bar stack inconclusive.":
    "启发式回退策略判断当前 K 线组合结论不足，先维持观望。",
};

const STRATEGY_LABEL_MAP: Record<string, string> = {
  baseline_momentum_v1: "只做多阈值动量",
  ai_bar_judge_v1: "AI K 线判断",
};

const POSITION_TIER_LABEL_MAP: Record<string, string> = {
  full: "满仓目标仓位",
  reduced: "试探仓位",
  hold: "维持现有仓位",
  risk_exit: "风控离场",
  exit: "离场",
  flat: "空仓等待",
  warmup: "预热阶段",
};

function normalizeText(value: string | null | undefined): string {
  return value?.trim() ?? "";
}

function containsChinese(value: string): boolean {
  return /[\u3400-\u9fff]/.test(value);
}

function formatPercentValue(
  value: string | number | null | undefined,
  fractionDigits = 4,
): string {
  if (value === null || value === undefined || value === "") {
    return "--";
  }
  return `${formatDecimal(value, fractionDigits)}%`;
}

function formatPercentRatio(
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

  return `${formatDecimal(numeric * 100, fractionDigits)}%`;
}

function formatPositionTier(value: string): string {
  return POSITION_TIER_LABEL_MAP[value] ?? titleCase(value);
}

function buildBaselineLogic(manifest: BacktestManifestSnapshot): string {
  const parameters = manifest.parameterSnapshot;
  return [
    `先观察最近 ${parameters.trend_lookback_bars ?? "--"} 根 K 线，确认其中至少 ${
      parameters.min_trend_up_bars ?? "--"
    } 次收盘上涨后，才允许把动量信号转成入场动作。`,
    `收盘价相对前收的动量达到 ${formatPercentRatio(parameters.entry_threshold_pct)} 才入场；`,
    `若强度不够高，则先用 ${formatPercentRatio(parameters.reduced_target_ratio)} 的试探仓。`,
  ].join("");
}

function buildBaselineSafety(manifest: BacktestManifestSnapshot): string {
  const parameters = manifest.parameterSnapshot;
  return `持仓后若动量回落到 ${formatPercentRatio(
    parameters.exit_threshold_pct,
  )} 或跌破 ${formatPercentRatio(parameters.trailing_stop_pct)} 的移动止盈阈值，就会退出。`;
}

function buildAiLogic(manifest: BacktestManifestSnapshot): string {
  const parameters = manifest.parameterSnapshot;
  return `先收集最近 ${parameters.lookback_bars ?? "--"} 根 K 线，再让模型输出买入、离场或观望；只有置信度不低于 ${
    parameters.min_confidence ?? "--"
  } 的判断，才会转成可执行信号。`;
}

function buildAiSafety(manifest: BacktestManifestSnapshot): string {
  const parameters = manifest.parameterSnapshot;
  const providerMode = titleCase(parameters.provider_mode ?? "heuristic_stub");
  return `默认提供方为 ${providerMode}；如果外部模型失败或超时，页面会把回退与压制原因写进审计信息，方便复盘。`;
}

function formatStrategyParameters(manifest: BacktestManifestSnapshot): string {
  const parameters = manifest.parameterSnapshot;
  if (manifest.strategyId === "baseline_momentum_v1") {
    return [
      `目标仓位 ${parameters.target_position ?? "--"} 股`,
      `入场阈值 ${formatPercentRatio(parameters.entry_threshold_pct)}`,
      `强势阈值 ${formatPercentRatio(parameters.strong_entry_threshold_pct)}`,
      `移动止盈 ${formatPercentRatio(parameters.trailing_stop_pct)}`,
    ].join(" / ");
  }
  if (manifest.strategyId === "ai_bar_judge_v1") {
    return [
      `观察窗口 ${parameters.lookback_bars ?? "--"} 根`,
      `目标仓位 ${parameters.target_position ?? "--"} 股`,
      `最低置信度 ${parameters.min_confidence ?? "--"}`,
      `入场阈值 ${formatPercentRatio(parameters.entry_threshold_pct)}`,
    ].join(" / ");
  }

  const fallbackPairs = Object.entries(parameters)
    .slice(0, 4)
    .map(([key, value]) => `${titleCase(key)} ${value}`);
  return fallbackPairs.join(" / ") || "当前策略没有额外参数快照。";
}

export function formatResearchStrategyName(strategyId: string | null | undefined): string {
  if (!strategyId) {
    return "未知策略";
  }
  return STRATEGY_LABEL_MAP[strategyId] ?? titleCase(strategyId);
}

export function localizeStrategyDescription(
  description: string | null | undefined,
  strategyId: string | null | undefined,
): string {
  const normalizedDescription = normalizeText(description);
  if (!normalizedDescription && strategyId) {
    return formatResearchStrategyName(strategyId);
  }
  if (containsChinese(normalizedDescription)) {
    return normalizedDescription;
  }
  return STRATEGY_DESCRIPTION_MAP[normalizedDescription] ?? normalizedDescription;
}

export function describeResearchStrategyLogic(
  manifest: BacktestManifestSnapshot | null | undefined,
): string {
  if (!manifest) {
    return "等待回测结果返回后补充当前策略的决策逻辑。";
  }
  if (manifest.strategyId === "baseline_momentum_v1") {
    return buildBaselineLogic(manifest);
  }
  if (manifest.strategyId === "ai_bar_judge_v1") {
    return buildAiLogic(manifest);
  }
  return localizeStrategyDescription(manifest.description, manifest.strategyId);
}

export function describeResearchStrategySafety(
  manifest: BacktestManifestSnapshot | null | undefined,
): string {
  if (!manifest) {
    return "等待回测结果返回后补充当前策略的风控与执行说明。";
  }
  if (manifest.strategyId === "baseline_momentum_v1") {
    return buildBaselineSafety(manifest);
  }
  if (manifest.strategyId === "ai_bar_judge_v1") {
    return buildAiSafety(manifest);
  }
  return "当前策略的额外风控说明暂未归纳。";
}

export function summarizeResearchStrategyParameters(
  manifest: BacktestManifestSnapshot | null | undefined,
): string {
  if (!manifest) {
    return "等待参数快照";
  }
  return formatStrategyParameters(manifest);
}

export function localizeResearchReason(reason: string | null | undefined): string {
  const normalizedReason = normalizeText(reason);
  if (!normalizedReason) {
    return "";
  }
  if (containsChinese(normalizedReason)) {
    return normalizedReason;
  }
  if (DIRECT_REASON_MAP[normalizedReason]) {
    return DIRECT_REASON_MAP[normalizedReason];
  }

  const aiWarmupMatch = normalizedReason.match(
    /^Waiting for AI lookback warmup before the first model decision \((\d+)\/(\d+) bars collected\)\.$/,
  );
  if (aiWarmupMatch) {
    return `AI 策略正在预热，首次模型判断前需要先收集足够 K 线（已收集 ${aiWarmupMatch[1]}/${aiWarmupMatch[2]} 根）。`;
  }

  const baselineWarmupMatch = normalizedReason.match(
    /^Waiting for enough finalized bars before the first confirmed baseline decision \((\d+)\/(\d+) bars collected\)\.$/,
  );
  if (baselineWarmupMatch) {
    return `基线策略正在预热，首次确认趋势前需要先收集足够已收盘 K 线（已收集 ${baselineWarmupMatch[1]}/${baselineWarmupMatch[2]} 根）。`;
  }

  const providerErrorMatch = normalizedReason.match(/^AI provider error was suppressed: (.+)$/);
  if (providerErrorMatch) {
    return `AI 服务调用失败，但这次回测已压制异常并继续执行：${localizeResearchReason(
      providerErrorMatch[1],
    ) || localizeMessage(providerErrorMatch[1]) || providerErrorMatch[1]}。`;
  }

  const confidenceGateMatch = normalizedReason.match(
    /^(.*) \(confidence ([\d.]+) < min ([\d.]+)\)$/,
  );
  if (confidenceGateMatch) {
    return `${localizeResearchReason(confidenceGateMatch[1])}由于置信度 ${
      confidenceGateMatch[2]
    } 低于最小要求 ${confidenceGateMatch[3]}，本次不执行交易。`;
  }

  const trailingStopMatch = normalizedReason.match(
    /^close ([\d.-]+) breached trailing_stop ([\d.-]+); peak_close_since_entry ([\d.-]+); flatten$/,
  );
  if (trailingStopMatch) {
    return `收盘价 ${trailingStopMatch[1]} 已跌破移动止盈线 ${trailingStopMatch[2]}（入场后最高收盘价 ${trailingStopMatch[3]}），因此执行清仓。`;
  }

  const exitMatch = normalizedReason.match(
    /^close ([\d.-]+) vs previous_close ([\d.-]+); momentum_pct ([\d.-]+) <= exit_threshold_pct ([\d.-]+); flatten$/,
  );
  if (exitMatch) {
    return `收盘价 ${exitMatch[1]} 相对前收 ${exitMatch[2]} 的动量为 ${formatPercentValue(
      exitMatch[3],
    )}，已经低于离场阈值 ${formatPercentValue(exitMatch[4])}，因此执行清仓。`;
  }

  const rebalanceMatch = normalizedReason.match(
    /^close ([\d.-]+) vs previous_close ([\d.-]+); momentum_pct ([\d.-]+) >= entry_threshold_pct ([\d.-]+); trend_return_pct ([\d.-]+); positive_close_changes (\d+)\/(\d+); position_tier ([a-z_]+); rebalance to ([\d.-]+)$/,
  );
  if (rebalanceMatch) {
    return `收盘价 ${rebalanceMatch[1]} 相对前收 ${rebalanceMatch[2]} 的动量为 ${formatPercentValue(
      rebalanceMatch[3],
    )}，达到入场阈值 ${formatPercentValue(rebalanceMatch[4])}；趋势区间涨幅为 ${formatPercentValue(
      rebalanceMatch[5],
    )}，最近 ${rebalanceMatch[7]} 根比较里有 ${rebalanceMatch[6]} 次上涨，因此按 ${formatPositionTier(
      rebalanceMatch[8],
    )} 调仓到 ${rebalanceMatch[9]} 股。`;
  }

  const holdTargetMatch = normalizedReason.match(
    /^close ([\d.-]+) vs previous_close ([\d.-]+); momentum_pct ([\d.-]+) stayed above exit_threshold_pct ([\d.-]+) but below entry_threshold_pct ([\d.-]+); hold current target ([\d.-]+)$/,
  );
  if (holdTargetMatch) {
    return `收盘价 ${holdTargetMatch[1]} 相对前收 ${holdTargetMatch[2]} 的动量为 ${formatPercentValue(
      holdTargetMatch[3],
    )}，仍高于离场阈值 ${formatPercentValue(holdTargetMatch[4])}，但还没达到入场阈值 ${formatPercentValue(
      holdTargetMatch[5],
    )}，所以继续保持当前目标仓位 ${holdTargetMatch[6]} 股。`;
  }

  const thresholdMissMatch = normalizedReason.match(
    /^close ([\d.-]+) vs previous_close ([\d.-]+); momentum_pct ([\d.-]+) below entry_threshold_pct ([\d.-]+); no position change$/,
  );
  if (thresholdMissMatch) {
    return `收盘价 ${thresholdMissMatch[1]} 相对前收 ${thresholdMissMatch[2]} 的动量为 ${formatPercentValue(
      thresholdMissMatch[3],
    )}，低于入场阈值 ${formatPercentValue(thresholdMissMatch[4])}，因此这一步不调整仓位。`;
  }

  const trendPendingMatch = normalizedReason.match(
    /^trend confirmation pending: trend_return_pct ([\d.-]+); positive_close_changes (\d+)\/(\d+); skip entry$/,
  );
  if (trendPendingMatch) {
    return `趋势确认还没完成：区间涨幅为 ${formatPercentValue(
      trendPendingMatch[1],
    )}，最近 ${trendPendingMatch[3]} 根比较里只有 ${trendPendingMatch[2]} 次上涨，因此先跳过入场。`;
  }

  return normalizedReason;
}

export function describeResearchSkipReason(
  decision: BacktestDecisionSnapshot,
): string | null {
  const skipReason = normalizeText(decision.skipReason);
  if (!skipReason) {
    return null;
  }

  switch (skipReason) {
    case "ai_decision_hold":
      return "模型明确给出了观望动作，所以这一步只记录判断，不生成交易信号。";
    case "ai_decision_below_min_confidence":
      return "模型虽然给了方向，但置信度没有达到最小要求，所以不会下单。";
    case "ai_lookback_warmup":
      return "AI 策略还在等待足够多的历史 K 线，样本不足时不会触发第一次模型判断。";
    case "ai_provider_error_suppressed":
      return "外部模型请求失败后，这次回测没有中断，而是压制错误并把原因记进审计。";
    case "baseline_trend_warmup":
      return "基线动量策略还在收集足够的已收盘 K 线，预热完成前不会贸然入场。";
    case "baseline_trend_unconfirmed":
      return "虽然在观察行情，但趋势确认条件还不够，所以这一步继续空仓等待。";
    case "baseline_entry_threshold_not_met":
      return "趋势方向虽然基本成立，但价格动量还没超过入场阈值，因此先不加仓。";
    case "strategy_returned_none":
      return "策略没有返回任何信号对象，所以回测只能把这一步记成跳过。";
    case "missing_symbol_rule":
      return "当前标的缺少交易规则配置，无法生成合法的下单计划。";
    case "missing_market_context":
      return "当前 bar 缺少前收、涨跌停等市场上下文，因此无法计算执行计划。";
    case "target_position_already_satisfied":
      return "当前持仓已经等于目标仓位，再下单只会重复，所以直接跳过。";
    case "sellable_qty_exhausted":
      return "这一步原本想卖出，但可卖数量已经用尽，所以计划无法执行。";
    case "normalized_buy_qty_below_min_qty":
      return "买入数量按最小交易单位归一化后不足一手，因此不会下单。";
    case "normalized_sell_qty_below_min_qty":
      return "卖出数量按最小交易单位归一化后不足一手，因此不会下单。";
    default:
      return `当前步骤被标记为 ${titleCase(skipReason)}，可结合下方原因摘要继续排查。`;
  }
}
