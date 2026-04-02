import type {
  BacktestDecisionSnapshot,
  CandleBar,
  CurvePoint,
  ResearchSnapshot,
  ResearchSnapshotCatalog,
} from "../types/research";

const DEFAULT_SYMBOL = "600036.SH";
const DEFAULT_TIMEFRAME = "15m";
const FIXTURE_SOURCE_LABEL = "与第 8 阶段回测结果契约对齐的本地多标的示例数据";

function roundPrice(value: number): number {
  return Number(value.toFixed(2));
}

function roundCurveValue(value: number): number {
  return Number(value.toFixed(4));
}

function mapBars(
  bars: CandleBar[],
  transform: (bar: CandleBar, index: number) => CandleBar,
): CandleBar[] {
  return bars.map((bar, index) => transform(bar, index));
}

function mapCurve(
  points: CurvePoint[],
  transform: (point: CurvePoint, index: number) => CurvePoint,
): CurvePoint[] {
  return points.map((point, index) => transform(point, index));
}

function aggregateBars(bars: CandleBar[], size: number): CandleBar[] {
  const aggregated: CandleBar[] = [];
  for (let index = 0; index < bars.length; index += size) {
    const chunk = bars.slice(index, index + size);
    if (chunk.length === 0) {
      continue;
    }
    aggregated.push({
      time: chunk[chunk.length - 1].time,
      open: chunk[0].open,
      high: Math.max(...chunk.map((bar) => bar.high)),
      low: Math.min(...chunk.map((bar) => bar.low)),
      close: chunk[chunk.length - 1].close,
      volume: chunk.reduce((sum, bar) => sum + bar.volume, 0),
    });
  }
  return aggregated;
}

function sampleCurve(points: CurvePoint[], size: number): CurvePoint[] {
  return points
    .filter((_, index) => (index + 1) % size === 0 || index === points.length - 1)
    .map((point) => ({ ...point }));
}

function replaceDecisionScope(
  decision: BacktestDecisionSnapshot,
  options: {
    symbol: string;
    timeframe: string;
  },
): BacktestDecisionSnapshot {
  const { symbol, timeframe } = options;
  const parts = decision.barKey.split(":");
  const suffix = parts.slice(2).join(":");
  return {
    ...decision,
    symbol,
    barKey: [symbol, timeframe, suffix].join(":"),
  };
}

function buildSymbolVariant(
  base: ResearchSnapshot,
  options: {
    symbol: string;
    priceMultiplier: number;
    priceOffset: number;
    volumeMultiplier: number;
    runtimeCurveOffset: number;
    runtimeCurveStep: number;
    backtestCurveOffset: number;
    backtestCurveStep: number;
    performanceDelta: number;
    totalReturnPct: number;
    maxDrawdownPct: number;
  },
): ResearchSnapshot {
  const {
    symbol,
    priceMultiplier,
    priceOffset,
    volumeMultiplier,
    runtimeCurveOffset,
    runtimeCurveStep,
    backtestCurveOffset,
    backtestCurveStep,
    performanceDelta,
    totalReturnPct,
    maxDrawdownPct,
  } = options;
  const transformedBars = mapBars(base.klineBars, (bar, index) => {
    const drift = index * 0.01;
    return {
      ...bar,
      open: roundPrice(bar.open * priceMultiplier + priceOffset + drift),
      high: roundPrice(bar.high * priceMultiplier + priceOffset + drift),
      low: roundPrice(bar.low * priceMultiplier + priceOffset + drift),
      close: roundPrice(bar.close * priceMultiplier + priceOffset + drift),
      volume: Math.round(bar.volume * volumeMultiplier),
    };
  });

  const runtimePnlCurve = mapCurve(base.runtimePnlCurve, (point, index) => ({
    ...point,
    value: roundCurveValue(point.value + runtimeCurveOffset + runtimeCurveStep * index),
    baseline:
      point.baseline === undefined
        ? undefined
        : roundCurveValue(point.baseline + runtimeCurveOffset),
  }));

  const backtestEquityCurve = mapCurve(base.backtestEquityCurve, (point, index) => ({
    ...point,
    value: roundCurveValue(point.value + backtestCurveOffset + backtestCurveStep * index),
    baseline:
      point.baseline === undefined
        ? undefined
        : roundCurveValue(point.baseline + backtestCurveOffset),
  }));

  return {
    ...base,
    datasetName: `CN Equity / ${symbol} / ${base.manifest.timeframe}`,
    sourceLabel: FIXTURE_SOURCE_LABEL,
    klineBars: transformedBars,
    runtimePnlCurve,
    backtestEquityCurve,
    manifest: {
      ...base.manifest,
      symbols: [symbol],
      dataFingerprint: `bars:${symbol}:${base.manifest.timeframe}:20260401-20260402:demo-fixture`,
      manifestFingerprint: `run:${base.manifest.strategyId}:${symbol}:${base.manifest.timeframe}:fixture-v2`,
    },
    performance: {
      ...base.performance,
      endingCash: roundCurveValue(base.performance.endingCash + performanceDelta),
      endingEquity: roundCurveValue(base.performance.endingEquity + performanceDelta),
      netPnl: roundCurveValue(base.performance.netPnl + performanceDelta),
      totalReturnPct,
      maxDrawdownPct,
      realizedPnl: roundCurveValue(base.performance.realizedPnl + performanceDelta),
      winRatePct: 50,
      winningTradeCount: 1,
      losingTradeCount: 1,
    },
    decisions: base.decisions.map((decision) =>
      replaceDecisionScope(decision, {
        symbol,
        timeframe: base.manifest.timeframe,
      }),
    ),
    notes: [
      "市场页和研究页现在都支持按 symbol/timeframe 在前端切换。",
      "研究页当前仍使用本地示例目录；仓库同时已经提供 `python -m apps.research` CLI 生成真实回测导出。",
      "这些示例字段与 Python 服务层中的 BacktestRunResult 语义保持一致。",
      "等 research HTTP 接口就绪后，可以直接复用这套 symbol/timeframe 视图切换结构。",
    ],
  };
}

function buildTimeframeVariant(
  base: ResearchSnapshot,
  timeframe: string,
): ResearchSnapshot {
  if (timeframe === base.manifest.timeframe) {
    return {
      ...base,
      klineBars: base.klineBars.map((bar) => ({ ...bar })),
      runtimePnlCurve: base.runtimePnlCurve.map((point) => ({ ...point })),
      backtestEquityCurve: base.backtestEquityCurve.map((point) => ({ ...point })),
      decisions: base.decisions.map((decision) => ({ ...decision })),
      notes: [...base.notes],
    };
  }

  const klineBars = aggregateBars(base.klineBars, 4);
  const runtimePnlCurve = sampleCurve(base.runtimePnlCurve, 4);
  const backtestEquityCurve = sampleCurve(base.backtestEquityCurve, 3);
  const symbol = base.manifest.symbols[0] ?? DEFAULT_SYMBOL;

  return {
    ...base,
    datasetName: `CN Equity / ${symbol} / ${timeframe}`,
    klineBars,
    runtimePnlCurve,
    backtestEquityCurve,
    manifest: {
      ...base.manifest,
      timeframe,
      barCount: klineBars.length,
      dataFingerprint: `bars:${symbol}:${timeframe}:20260401-20260402:demo-fixture`,
      manifestFingerprint: `run:${base.manifest.strategyId}:${symbol}:${timeframe}:fixture-v2`,
    },
    performance: {
      ...base.performance,
      barCount: backtestEquityCurve.length,
    },
    decisions: base.decisions.map((decision) =>
      replaceDecisionScope(decision, {
        symbol,
        timeframe,
      }),
    ),
  };
}

const baseResearchSnapshot: ResearchSnapshot = {
  datasetName: "CN Equity / 600036.SH / 15m",
  sourceLabel: FIXTURE_SOURCE_LABEL,
  sourceMode: "fixture",
  klineBars: [
    {
      time: "2026-04-02T09:45:00+08:00",
      open: 39.41,
      high: 39.48,
      low: 39.36,
      close: 39.46,
      volume: 118000,
    },
    {
      time: "2026-04-02T10:00:00+08:00",
      open: 39.46,
      high: 39.52,
      low: 39.42,
      close: 39.49,
      volume: 126000,
    },
    {
      time: "2026-04-02T10:15:00+08:00",
      open: 39.49,
      high: 39.58,
      low: 39.47,
      close: 39.56,
      volume: 152000,
    },
    {
      time: "2026-04-02T10:30:00+08:00",
      open: 39.56,
      high: 39.61,
      low: 39.5,
      close: 39.53,
      volume: 143000,
    },
    {
      time: "2026-04-02T10:45:00+08:00",
      open: 39.53,
      high: 39.65,
      low: 39.51,
      close: 39.62,
      volume: 171000,
    },
    {
      time: "2026-04-02T11:00:00+08:00",
      open: 39.62,
      high: 39.68,
      low: 39.55,
      close: 39.58,
      volume: 168000,
    },
    {
      time: "2026-04-02T13:15:00+08:00",
      open: 39.58,
      high: 39.66,
      low: 39.54,
      close: 39.63,
      volume: 132000,
    },
    {
      time: "2026-04-02T13:30:00+08:00",
      open: 39.63,
      high: 39.71,
      low: 39.6,
      close: 39.69,
      volume: 149000,
    },
    {
      time: "2026-04-02T13:45:00+08:00",
      open: 39.69,
      high: 39.73,
      low: 39.61,
      close: 39.64,
      volume: 141000,
    },
    {
      time: "2026-04-02T14:00:00+08:00",
      open: 39.64,
      high: 39.7,
      low: 39.57,
      close: 39.6,
      volume: 156000,
    },
    {
      time: "2026-04-02T14:15:00+08:00",
      open: 39.6,
      high: 39.67,
      low: 39.55,
      close: 39.65,
      volume: 137000,
    },
    {
      time: "2026-04-02T14:30:00+08:00",
      open: 39.65,
      high: 39.74,
      low: 39.63,
      close: 39.72,
      volume: 182000,
    },
  ],
  runtimePnlCurve: [
    { time: "2026-04-02T09:45:00+08:00", value: 100000, baseline: 100000 },
    { time: "2026-04-02T10:00:00+08:00", value: 100018, baseline: 100000 },
    {
      time: "2026-04-02T10:15:00+08:00",
      value: 100062,
      baseline: 100000,
      annotation: "动量入场",
    },
    { time: "2026-04-02T10:30:00+08:00", value: 100041, baseline: 100000 },
    { time: "2026-04-02T10:45:00+08:00", value: 100088, baseline: 100000 },
    { time: "2026-04-02T11:00:00+08:00", value: 100071, baseline: 100000 },
    { time: "2026-04-02T13:15:00+08:00", value: 100094, baseline: 100000 },
    { time: "2026-04-02T13:30:00+08:00", value: 100122, baseline: 100000 },
    { time: "2026-04-02T13:45:00+08:00", value: 100101, baseline: 100000 },
    { time: "2026-04-02T14:00:00+08:00", value: 100084, baseline: 100000 },
    { time: "2026-04-02T14:15:00+08:00", value: 100113, baseline: 100000 },
    {
      time: "2026-04-02T14:30:00+08:00",
      value: 100149,
      baseline: 100000,
      annotation: "收盘接近日高",
    },
  ],
  backtestEquityCurve: [
    { time: "2026-04-01T14:00:00+08:00", value: 100000, baseline: 100000 },
    {
      time: "2026-04-01T14:15:00+08:00",
      value: 99985.22,
      baseline: 100000,
      annotation: "开仓手续费",
    },
    { time: "2026-04-01T14:30:00+08:00", value: 99971.8, baseline: 100000 },
    { time: "2026-04-01T14:45:00+08:00", value: 99956.1, baseline: 100000 },
    { time: "2026-04-02T10:00:00+08:00", value: 99944.78, baseline: 100000 },
    { time: "2026-04-02T10:15:00+08:00", value: 99929.56, baseline: 100000 },
    {
      time: "2026-04-02T10:30:00+08:00",
      value: 99926.34,
      baseline: 100000,
      annotation: "离场确认",
    },
  ],
  manifest: {
    runId: "1f4caa07-8d2c-4d79-8fc8-d9e1d670b57d",
    accountId: "paper_account_001",
    strategyId: "baseline_momentum_v1",
    handlerName: "BaselineMomentumStrategy",
    description: "复用生产基线动量逻辑的最小事件驱动回放。",
    symbols: ["600036.SH"],
    timeframe: "15m",
    barCount: 7,
    startTime: "2026-04-01T14:00:00+08:00",
    endTime: "2026-04-02T10:30:00+08:00",
    initialCash: 100000,
    slippageBps: 5,
    feeModel: "ashare_paper_cost_model",
    slippageModel: "bar_close_bps",
    dataFingerprint: "bars:600036.SH:15m:20260401-20260402:demo-fixture",
    manifestFingerprint: "run:baseline_momentum_v1:600036.SH:15m:fixture-v2",
  },
  performance: {
    barCount: 7,
    signalCount: 3,
    orderCount: 2,
    tradeCount: 2,
    fillCount: 2,
    winningTradeCount: 0,
    losingTradeCount: 1,
    startingCash: 100000,
    endingCash: 99926.3404,
    endingMarketValue: 0,
    startingEquity: 100000,
    endingEquity: 99926.3404,
    netPnl: -73.6596,
    totalReturnPct: -0.0737,
    maxDrawdownPct: 0.0737,
    realizedPnl: -73.6596,
    unrealizedPnl: 0,
    turnover: 7890,
    winRatePct: 0,
  },
  decisions: [
    {
      barKey: "600036.SH:15m:2026-04-01T14:00:00+08:00",
      eventTime: "2026-04-01T14:00:00+08:00",
      symbol: "600036.SH",
      signalType: "REBALANCE",
      action: "BUY",
      targetPosition: 200,
      reasonSummary: "价格上破前收阈值后建立试探性仓位。",
      skipReason: null,
      fillCount: 1,
      orderPlanSide: "BUY",
    },
    {
      barKey: "600036.SH:15m:2026-04-01T14:15:00+08:00",
      eventTime: "2026-04-01T14:15:00+08:00",
      symbol: "600036.SH",
      signalType: "REBALANCE",
      action: "SKIP",
      targetPosition: 0,
      reasonSummary: "生成了卖出意图，但在当日可卖数量约束下不可执行。",
      skipReason: "sellable_qty_exhausted",
      fillCount: 0,
      orderPlanSide: null,
    },
    {
      barKey: "600036.SH:15m:2026-04-02T10:00:00+08:00",
      eventTime: "2026-04-02T10:00:00+08:00",
      symbol: "600036.SH",
      signalType: "REBALANCE",
      action: "SELL",
      targetPosition: 0,
      reasonSummary: "下一交易日低开于参考价下方，因此完成平仓。",
      skipReason: null,
      fillCount: 1,
      orderPlanSide: "SELL",
    },
  ],
  notes: [
    "市场页和研究页现在都支持按 symbol/timeframe 在前端切换。",
    "研究页当前仍使用本地示例目录；仓库同时已经提供 `python -m apps.research` CLI 生成真实回测导出。",
    "这些示例字段与 Python 服务层中的 BacktestRunResult 语义保持一致。",
    "等 research HTTP 接口就绪后，可以直接复用这套 symbol/timeframe 视图切换结构。",
  ],
};

const secondSymbolSnapshot = buildSymbolVariant(baseResearchSnapshot, {
  symbol: "000001.SZ",
  priceMultiplier: 0.31,
  priceOffset: -0.12,
  volumeMultiplier: 1.28,
  runtimeCurveOffset: -48,
  runtimeCurveStep: 6,
  backtestCurveOffset: 92,
  backtestCurveStep: 5,
  performanceDelta: 92.4418,
  totalReturnPct: 0.0188,
  maxDrawdownPct: 0.0512,
});

export const researchSnapshotCatalog: ResearchSnapshotCatalog = {
  "600036.SH": {
    "15m": buildTimeframeVariant(baseResearchSnapshot, "15m"),
    "1h": buildTimeframeVariant(baseResearchSnapshot, "1h"),
  },
  "000001.SZ": {
    "15m": buildTimeframeVariant(secondSymbolSnapshot, "15m"),
    "1h": buildTimeframeVariant(secondSymbolSnapshot, "1h"),
  },
};

export const researchSnapshotFixture =
  researchSnapshotCatalog[DEFAULT_SYMBOL][DEFAULT_TIMEFRAME];

export function listResearchFixtureSymbols(): string[] {
  return Object.keys(researchSnapshotCatalog);
}

export function listResearchFixtureTimeframes(symbol: string): string[] {
  const symbolCatalog =
    researchSnapshotCatalog[symbol] ?? researchSnapshotCatalog[DEFAULT_SYMBOL];
  return Object.keys(symbolCatalog);
}

export function getResearchSnapshot(
  symbol: string,
  timeframe: string,
): ResearchSnapshot {
  const symbolCatalog =
    researchSnapshotCatalog[symbol] ?? researchSnapshotCatalog[DEFAULT_SYMBOL];
  return (
    symbolCatalog[timeframe] ??
    symbolCatalog[DEFAULT_TIMEFRAME] ??
    researchSnapshotFixture
  );
}
