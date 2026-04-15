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
  strategyVersion: string;
  handlerName: string;
  description: string;
  mode: ResearchMode;
  samplePurpose: ResearchSamplePurpose;
  symbol: string;
  symbols: string[];
  timeframe: string;
  barCount: number;
  startTime: string;
  endTime: string;
  generatedAt: string;
  initialCash: number;
  costModel: string;
  slippageBps: number;
  feeModel: string;
  slippageModel: string;
  partialFillModel?: string;
  unfilledQtyHandling?: string;
  executionConstraints?: string[];
  parameterSnapshot: Record<string, string>;
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
  sharpeRatio?: number | null;
  returnToDrawdownRatio?: number | null;
  profitFactor?: number | null;
  avgTradePnl?: number | null;
  avgWinningTradePnl?: number | null;
  avgLosingTradePnl?: number | null;
  avgHoldingBars?: number | null;
}

export interface BacktestDecisionSnapshot {
  barKey: string;
  eventTime: string;
  symbol: string;
  signalType: string | null;
  action: "ENTRY" | "EXIT" | "HOLD" | "REBALANCE" | "REDUCE" | "SKIP";
  executionAction: "BUY" | "SELL" | "SKIP";
  targetPosition: number | null;
  reasonSummary: string;
  audit?: StrategyDecisionAuditSummarySnapshot | null;
  skipReason: string | null;
  fillCount: number;
  orderPlanSide: string | null;
}

export interface StrategyDecisionAuditSummarySnapshot {
  providerId: string | null;
  modelOrPolicyVersion: string | null;
  decision: string | null;
  confidence: string | null;
  reasonSummary: string | null;
  fallbackUsed: boolean | null;
  fallbackReason: string | null;
}

export type ResearchAiProvider = "heuristic_stub" | "openai_compatible";
export type ResearchMode =
  | "preview"
  | "evaluation"
  | "parameter_scan"
  | "walk_forward";

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

export const RULE_RESEARCH_TEMPLATE_MOVING_AVERAGE_BAND_V1 =
  "moving_average_band_v1";
export const RULE_RESEARCH_REQUIRED_TIMEFRAME = "1d";

export type ResearchRuleTemplate =
  typeof RULE_RESEARCH_TEMPLATE_MOVING_AVERAGE_BAND_V1;

export interface MovingAverageBandRuleConfig {
  // Counts 1d bars only. MA60 means 60 daily bars, not 60 bars of the current UI timeframe.
  maWindow: number;
  // 0.05 means close <= ma * (1 - 0.05).
  buyBelowMaPct: number;
  // 0.10 means close >= ma * (1 + 0.10).
  sellAboveMaPct: number;
  // Continues the existing backtest semantics: absolute share count, not portfolio ratio.
  targetPosition: number;
}

export interface ResearchRuleSnapshotRequest {
  symbol?: string;
  // Rule backtests pin the first MVP to daily bars so MA semantics stay unambiguous.
  timeframe: typeof RULE_RESEARCH_REQUIRED_TIMEFRAME;
  limit?: number;
  initialCash?: number;
  slippageBps?: number;
  ruleTemplate: ResearchRuleTemplate;
  ruleConfig: MovingAverageBandRuleConfig;
}

export type ResearchSnapshotSourceMode = "fixture" | "imported" | "live";
export type ResearchSamplePurpose = "preview" | "evaluation";

export interface ResearchSummarySnapshot {
  mode: ResearchMode;
  modeLabel: string;
  resultHeadline: string;
  sampleMessage: string;
  comparisonMessage: string | null;
}

export interface ResearchSampleSnapshot {
  purpose: ResearchSamplePurpose;
  label: string;
  requestedBarCount: number;
  actualBarCount: number;
  supportsTimeSegmentation: boolean;
  segmentCount: number;
  description: string;
  warning: string | null;
}

export interface ResearchSegmentSnapshot {
  label: string;
  marketRegime: "uptrend" | "sideways" | "downtrend";
  marketRegimeLabel: string;
  startTime: string;
  endTime: string;
  barCount: number;
  priceChangePct: number;
  performance: BacktestPerformanceSnapshot;
}

export interface ResearchPerformanceDeltaSnapshot {
  netPnlDelta: number;
  totalReturnDeltaPct: number;
  maxDrawdownDeltaPct: number;
  tradeCountDelta: number;
  turnoverDelta: number;
}

export interface ResearchComparisonDecisionDiff {
  barKey: string;
  eventTime: string;
  baselineAction: string;
  candidateAction: string;
  baselineReason: string;
  candidateReason: string;
}

export interface ResearchComparisonSnapshot {
  baselineLabel: string;
  candidateLabel: string;
  candidateKind: "parameter_scan_best_variant" | "ai_strategy";
  sameSample: boolean;
  sameMetricSemantics: boolean;
  netPnlDelta: number;
  totalReturnDeltaPct: number;
  maxDrawdownDeltaPct: number;
  tradeCountDelta: number;
  turnoverDelta: number;
  decisionDiffCount: number;
  decisionDiffs: ResearchComparisonDecisionDiff[];
  summaryMessage: string;
}

export interface ResearchParameterScanVariantSnapshot {
  label: string;
  strategyId: string;
  handlerName: string;
  parameters: Record<string, string>;
  performance: BacktestPerformanceSnapshot;
  manifestFingerprint: string;
  versusBaseline: ResearchPerformanceDeltaSnapshot;
}

export interface ResearchParameterScanSnapshot {
  strategyId: string;
  combinationCount: number;
  rankingMetric: string;
  bestVariantLabel: string | null;
  bestVariant: ResearchParameterScanVariantSnapshot | null;
  variants: ResearchParameterScanVariantSnapshot[];
}

export interface ResearchWalkForwardWindowSnapshot {
  label: string;
  startTime: string;
  endTime: string;
  barCount: number;
  performance: BacktestPerformanceSnapshot;
  manifestFingerprint: string;
}

export interface ResearchWalkForwardSnapshot {
  method: string;
  strategyId: string;
  windowBars: number;
  stepBars: number;
  windowCount: number;
  bestWindowLabel: string | null;
  bestWindow: ResearchWalkForwardWindowSnapshot | null;
  positiveWindowCount: number;
  windows: ResearchWalkForwardWindowSnapshot[];
}

export interface ResearchExperimentsSnapshot {
  parameterScan?: ResearchParameterScanSnapshot;
  walkForward?: ResearchWalkForwardSnapshot;
}

export interface ResearchSnapshot {
  datasetName: string;
  sourceLabel: string;
  sourceMode: ResearchSnapshotSourceMode;
  mode: ResearchMode;
  summary: ResearchSummarySnapshot;
  klineBars: CandleBar[];
  equityCurve: CurvePoint[];
  manifest: BacktestManifestSnapshot;
  performance: BacktestPerformanceSnapshot;
  decisions: BacktestDecisionSnapshot[];
  sample?: ResearchSampleSnapshot | null;
  segments?: ResearchSegmentSnapshot[];
  experiments?: ResearchExperimentsSnapshot | null;
  comparison?: ResearchComparisonSnapshot | null;
  notes: string[];
}

export type ResearchSnapshotCatalog = Record<string, Record<string, ResearchSnapshot>>;

export type AppView = "operations" | "market" | "research";
