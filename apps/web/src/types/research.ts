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

export type ResearchAiProvider = "heuristic_stub" | "openai_compatible";

export interface ResearchAiSettings {
  accountId: string;
  provider: ResearchAiProvider;
  model: string;
  baseUrl: string;
  hasApiKey: boolean;
  apiKeyHint: string | null;
  updatedAt: string | null;
}

export interface ResearchAiSnapshotRequest {
  symbol?: string;
  timeframe?: string;
  limit?: number;
  provider: ResearchAiProvider;
  model?: string;
  baseUrl?: string;
  apiKey?: string;
}

export interface ResearchAiSettingsUpdateRequest {
  provider: ResearchAiProvider;
  model: string;
  baseUrl: string;
  apiKey?: string;
  clearApiKey?: boolean;
}

export type ResearchSnapshotSourceMode = "fixture" | "imported" | "live";

export interface ResearchSnapshot {
  datasetName: string;
  sourceLabel: string;
  sourceMode: ResearchSnapshotSourceMode;
  klineBars: CandleBar[];
  equityCurve: CurvePoint[];
  manifest: BacktestManifestSnapshot;
  performance: BacktestPerformanceSnapshot;
  decisions: BacktestDecisionSnapshot[];
  notes: string[];
}

export type ResearchSnapshotCatalog = Record<string, Record<string, ResearchSnapshot>>;

export type AppView = "operations" | "market" | "research";
