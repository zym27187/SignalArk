export interface CandleBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CurvePoint {
  time: string;
  value: number;
  baseline?: number;
  annotation?: string;
}

export interface BacktestManifestSnapshot {
  runId: string;
  accountId: string;
  strategyId: string;
  handlerName: string;
  description: string;
  symbols: string[];
  timeframe: string;
  barCount: number;
  startTime: string;
  endTime: string;
  initialCash: number;
  slippageBps: number;
  feeModel: string;
  slippageModel: string;
  dataFingerprint: string;
  manifestFingerprint: string;
}

export interface BacktestPerformanceSnapshot {
  barCount: number;
  signalCount: number;
  orderCount: number;
  tradeCount: number;
  fillCount: number;
  winningTradeCount: number;
  losingTradeCount: number;
  startingCash: number;
  endingCash: number;
  endingMarketValue: number;
  startingEquity: number;
  endingEquity: number;
  netPnl: number;
  totalReturnPct: number;
  maxDrawdownPct: number;
  realizedPnl: number;
  unrealizedPnl: number;
  turnover: number;
  winRatePct: number | null;
}

export interface BacktestDecisionSnapshot {
  barKey: string;
  eventTime: string;
  symbol: string;
  signalType: string | null;
  action: "BUY" | "SELL" | "SKIP";
  targetPosition: number | null;
  reasonSummary: string;
  skipReason: string | null;
  fillCount: number;
  orderPlanSide: string | null;
}

export type ResearchSnapshotSourceMode = "fixture" | "live";

export interface ResearchSnapshot {
  datasetName: string;
  sourceLabel: string;
  sourceMode: ResearchSnapshotSourceMode;
  klineBars: CandleBar[];
  runtimePnlCurve: CurvePoint[];
  backtestEquityCurve: CurvePoint[];
  manifest: BacktestManifestSnapshot;
  performance: BacktestPerformanceSnapshot;
  decisions: BacktestDecisionSnapshot[];
  notes: string[];
}

export type ResearchSnapshotCatalog = Record<string, Record<string, ResearchSnapshot>>;

export type AppView = "operations" | "market" | "research";
