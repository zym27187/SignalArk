import { useEffect, useState } from "react";

import { AreaChart } from "../AreaChart";
import { BacktestDecisionTable } from "../BacktestDecisionTable";
import { DatasetSwitcher } from "../DatasetSwitcher";
import { DefinitionGrid } from "../DefinitionGrid";
import { MetricCard } from "../MetricCard";
import { SectionCard } from "../SectionCard";
import { useAiResearchData } from "../../hooks/use-ai-research-data";
import { useAiResearchSettings } from "../../hooks/use-ai-research-settings";
import type { ResearchDataState } from "../../hooks/use-research-data";
import { useRuleResearchData } from "../../hooks/use-rule-research-data";
import {
  DEFAULT_RULE_RESEARCH_TEMPLATE,
  DEFAULT_RULE_RESEARCH_TIMEFRAME,
  DEFAULT_RESEARCH_EVALUATION_LIMIT,
  DEFAULT_RESEARCH_PREVIEW_LIMIT,
  DEFAULT_AI_RESEARCH_PREVIEW_LIMIT,
  RULE_RESEARCH_HISTORY_YEAR_OPTIONS,
  resolveRuleResearchLookbackLimit,
  type RuleResearchHistoryYears,
} from "../../lib/api";
import {
  formatDateTime,
  formatDecimal,
  formatSignedMoney,
  formatSymbolLabel,
  formatSymbolList,
} from "../../lib/format";
import {
  describeResearchStrategyLogic,
  describeResearchStrategySafety,
  formatResearchStrategyName,
  localizeResearchReason,
  localizeStrategyDescription,
  summarizeResearchStrategyParameters,
} from "../../lib/research-copy";
import type { SymbolNameMap } from "../../types/api";
import type {
  ResearchAiProvider,
  ResearchMode,
  ResearchRuleSnapshotRequest,
  ResearchSnapshot,
} from "../../types/research";

interface ResearchViewProps {
  researchData: ResearchDataState;
  availableSymbols: string[];
  symbolNames: SymbolNameMap;
  availableTimeframes: string[];
  selectedSymbol: string;
  selectedTimeframe: string;
  selectedMode: ResearchMode;
  selectedRuleHistoryYears: RuleResearchHistoryYears;
  onSymbolChange: (symbol: string) => void;
  onTimeframeChange: (timeframe: string) => void;
  onModeChange: (mode: ResearchMode) => void;
  onRuleHistoryYearsChange: (years: RuleResearchHistoryYears) => void;
}

interface SnapshotSectionOptions {
  labelPrefix: string;
  eyebrow: string;
  chartTitle: string;
  chartDescription: string;
  chartAccent: "teal" | "amber" | "red";
  strategyEyebrow: string;
  strategyTitle: string;
  strategyDescription: string;
  decisionEyebrow: string;
  decisionTitle: string;
  decisionDescription: string;
  metadataEyebrow: string;
  metadataTitle: string;
  metadataDescription: string;
  notesEyebrow: string;
  notesTitle: string;
  notesDescription: string;
  emptyTitle: string;
  emptyCopy: string;
}

function buildMetadataItems(
  snapshot: ResearchSnapshot | null,
  {
    isLoading,
    error,
    symbolNames,
    waitingHint,
  }: {
    isLoading: boolean;
    error: string | null;
    symbolNames: SymbolNameMap;
    waitingHint: string;
  },
) {
  const manifest = snapshot?.manifest;
  const sample = snapshot?.sample;
  const summary = snapshot?.summary;
  if (manifest === undefined) {
    return [
      {
        label: "当前状态",
        value: isLoading ? "生成中" : "等待数据",
        hint: error ?? waitingHint,
      },
    ];
  }

  return [
    {
      label: "研究模式",
      value:
        summary === undefined
          ? "等待研究结果"
          : `${summary.modeLabel}${sample ? ` / ${sample.actualBarCount} 根 K 线` : ""}`,
      hint:
        sample === undefined || sample === null
          ? "返回结果后，这里会说明当前是预览、评估还是实验模式。"
          : summary?.sampleMessage ?? sample.warning ?? sample.description,
    },
    {
      label: "本次回测编号",
      value: manifest.runId,
      hint: localizeStrategyDescription(manifest.description, manifest.strategyId),
    },
    {
      label: "回测时间范围",
      value: `${formatDateTime(manifest.startTime)} 至 ${formatDateTime(manifest.endTime)}`,
    },
    {
      label: "账户与标的",
      value: `${manifest.accountId} / ${formatSymbolList(manifest.symbols, symbolNames)}`,
      hint: `${manifest.handlerName} · ${manifest.timeframe} · ${manifest.strategyVersion}`,
    },
    {
      label: "交易成本假设",
      value: `滑点 ${formatDecimal(manifest.slippageBps, 0)} bps`,
      hint: [
        manifest.feeModel,
        manifest.slippageModel,
        manifest.partialFillModel,
      ]
        .filter(Boolean)
        .join(" + "),
    },
    {
      label: "参数快照",
      value: `${Object.keys(manifest.parameterSnapshot).length} 个字段`,
      hint:
        Object.entries(manifest.parameterSnapshot)
          .slice(0, 4)
          .map(([key, value]) => `${key}=${value}`)
          .join(" / ") || "当前策略没有额外参数快照。",
    },
    {
      label: "执行约束",
      value: manifest.unfilledQtyHandling ?? "not_applicable_full_fill",
      hint:
        manifest.executionConstraints?.join(" / ") ??
        "返回结果后，这里会列出当前 backtest 与 paper/live 在执行层的剩余差异。",
    },
    {
      label: "数据版本标识",
      value: manifest.dataFingerprint,
    },
    {
      label: "配置版本标识",
      value: manifest.manifestFingerprint,
    },
  ];
}

function buildStrategyItems(
  snapshot: ResearchSnapshot | null,
  {
    isLoading,
    error,
    waitingHint,
  }: {
    isLoading: boolean;
    error: string | null;
    waitingHint: string;
  },
) {
  const manifest = snapshot?.manifest;
  if (manifest === undefined) {
    return [
      {
        label: "当前策略",
        value: isLoading ? "生成中" : "等待回测结果",
        hint: error ?? waitingHint,
      },
    ];
  }

  const parameterCount = Object.keys(manifest.parameterSnapshot).length;

  return [
    {
      label: "策略类型",
      value: formatResearchStrategyName(manifest.strategyId),
      hint: `${manifest.handlerName} · 版本 ${manifest.strategyVersion}`,
    },
    {
      label: "策略说明",
      value: localizeStrategyDescription(manifest.description, manifest.strategyId),
      hint: `策略 ID：${manifest.strategyId}`,
    },
    {
      label: "怎么判断买卖",
      value: describeResearchStrategyLogic(manifest),
      hint: describeResearchStrategySafety(manifest),
    },
    {
      label: "关键参数",
      value: summarizeResearchStrategyParameters(manifest),
      hint:
        parameterCount > 0
          ? `本次回测固化了 ${parameterCount} 个参数字段，方便你对照同样条件再次复现。`
          : "当前策略没有额外参数快照。",
    },
  ];
}

function formatRatioMetric(value: number | null | undefined): string {
  return value === null || value === undefined ? "--" : formatDecimal(value, 4);
}

function formatAverageHoldingBars(value: number | null | undefined): string {
  return value === null || value === undefined ? "--" : `${formatDecimal(value, 2)} 根`;
}

function buildResearchModeCopy(mode: ResearchMode): string {
  if (mode === "preview") {
    return `快速预览最近 ${DEFAULT_RESEARCH_PREVIEW_LIMIT} 根 K 线，更适合先看信号和审计。`;
  }
  if (mode === "parameter_scan") {
    return `默认使用 ${DEFAULT_RESEARCH_EVALUATION_LIMIT} 根 K 线的评估样本，外加 baseline 默认参数小网格扫描。`;
  }
  if (mode === "walk_forward") {
    return `默认使用 ${DEFAULT_RESEARCH_EVALUATION_LIMIT} 根 K 线的评估样本，并做滚动窗口稳定性检查。`;
  }
  return `默认使用 ${DEFAULT_RESEARCH_EVALUATION_LIMIT} 根 K 线的评估样本，并尽量补充分段验证。`;
}

function formatSignedCount(value: number): string {
  if (value > 0) {
    return `+${value}`;
  }
  return String(value);
}

export function ResearchView({
  researchData,
  availableSymbols,
  symbolNames,
  availableTimeframes,
  selectedSymbol,
  selectedTimeframe,
  selectedMode,
  selectedRuleHistoryYears,
  onSymbolChange,
  onTimeframeChange,
  onModeChange,
  onRuleHistoryYearsChange,
}: ResearchViewProps) {
  const aiResearchData = useAiResearchData();
  const ruleResearchData = useRuleResearchData();
  const aiSettings = useAiResearchSettings({ enabled: true });
  const [aiProvider, setAiProvider] = useState<ResearchAiProvider>("openai_compatible");
  const [aiModel, setAiModel] = useState("gpt-5.4");
  const [aiBaseUrl, setAiBaseUrl] = useState("https://api.openai.com/v1");
  const [aiApiKey, setAiApiKey] = useState("");
  const [clearSavedApiKey, setClearSavedApiKey] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);
  const [ruleStatusMessage, setRuleStatusMessage] = useState<string | null>(null);
  const [ruleMaWindow, setRuleMaWindow] = useState("60");
  const [ruleBuyBelowMaPct, setRuleBuyBelowMaPct] = useState("0.05");
  const [ruleSellAboveMaPct, setRuleSellAboveMaPct] = useState("0.10");
  const [ruleTargetPosition, setRuleTargetPosition] = useState("400");
  const [ruleInitialCash, setRuleInitialCash] = useState("100000");

  useEffect(() => {
    aiResearchData.reset();
  }, [selectedSymbol, selectedTimeframe, selectedMode]);

  useEffect(() => {
    ruleResearchData.reset();
    setRuleStatusMessage(null);
  }, [selectedSymbol, selectedRuleHistoryYears]);

  useEffect(() => {
    if (aiSettings.settings === null) {
      return;
    }
    setAiProvider(aiSettings.settings.provider);
    setAiModel(aiSettings.settings.model);
    setAiBaseUrl(aiSettings.settings.baseUrl);
    setAiApiKey("");
    setClearSavedApiKey(false);
  }, [aiSettings.settings]);

  const snapshot = researchData.snapshot;
  const ruleLookbackLimit = resolveRuleResearchLookbackLimit(selectedRuleHistoryYears);
  const primarySnapshot = ruleResearchData.snapshot ?? snapshot;
  const manifest = primarySnapshot?.manifest;
  const sample = primarySnapshot?.sample;
  const summary = primarySnapshot?.summary;
  const experiments = primarySnapshot?.experiments;
  const comparison = ruleResearchData.snapshot
    ? ruleResearchData.snapshot.comparison ?? null
    : aiResearchData.snapshot?.comparison ?? snapshot?.comparison ?? null;
  const sourceLabel = primarySnapshot
    ? primarySnapshot.sourceMode === "fixture"
      ? primarySnapshot.sourceLabel
      : primarySnapshot.manifest.strategyId === DEFAULT_RULE_RESEARCH_TEMPLATE
        ? "规则回测结果"
        : "真实回测结果"
    : researchData.isLoading
      ? "正在生成回测结果"
      : "等待回测数据";
  const sourceIsFixture = primarySnapshot?.sourceMode === "fixture";
  const primaryMetadataItems = buildMetadataItems(primarySnapshot, {
    isLoading:
      ruleResearchData.snapshot !== null ? ruleResearchData.isLoading : researchData.isLoading,
    error: ruleResearchData.snapshot !== null ? ruleResearchData.error : researchData.error,
    symbolNames,
    waitingHint:
      ruleResearchData.snapshot !== null
        ? "运行规则回测后，这里会生成一份完整的规则回测结果。"
        : "选择标的和周期后，这里会生成一份回测结果。",
  });
  const aiMetadataItems = buildMetadataItems(aiResearchData.snapshot, {
    isLoading: aiResearchData.isLoading,
    error: aiResearchData.error,
    symbolNames,
    waitingHint: `填好模型接入信息后，这里会生成一份 AI 回测快速预览（最近 ${DEFAULT_AI_RESEARCH_PREVIEW_LIMIT} 根 K 线）。`,
  });
  const savedApiKeyHint = aiSettings.settings?.hasApiKey ? aiSettings.settings.apiKeyHint : null;
  const latestAiSettingsUpdatedAt = aiSettings.settings?.updatedAt;

  function buildRuleRequest(
    overrides?: Partial<ResearchRuleSnapshotRequest>,
  ): ResearchRuleSnapshotRequest | null {
    const maWindow = Number(overrides?.ruleConfig?.maWindow ?? ruleMaWindow);
    const buyBelowMaPct = Number(overrides?.ruleConfig?.buyBelowMaPct ?? ruleBuyBelowMaPct);
    const sellAboveMaPct = Number(
      overrides?.ruleConfig?.sellAboveMaPct ?? ruleSellAboveMaPct,
    );
    const targetPosition = Number(
      overrides?.ruleConfig?.targetPosition ?? ruleTargetPosition,
    );
    const initialCash = Number(overrides?.initialCash ?? ruleInitialCash);
    const numericValues = [
      maWindow,
      buyBelowMaPct,
      sellAboveMaPct,
      targetPosition,
      initialCash,
    ];
    if (numericValues.some((value) => !Number.isFinite(value))) {
      setRuleStatusMessage("请先把规则参数填写完整，再运行规则回测。");
      return null;
    }

    return {
      symbol: selectedSymbol,
      timeframe: DEFAULT_RULE_RESEARCH_TIMEFRAME,
      limit: overrides?.limit ?? ruleLookbackLimit,
      initialCash,
      slippageBps: overrides?.slippageBps ?? 5,
      ruleTemplate: DEFAULT_RULE_RESEARCH_TEMPLATE,
      ruleConfig: {
        maWindow,
        buyBelowMaPct,
        sellAboveMaPct,
        targetPosition,
      },
    };
  }

  async function runRuleResearch(overrides?: Partial<ResearchRuleSnapshotRequest>) {
    const request = buildRuleRequest(overrides);
    if (request === null) {
      return;
    }
    const nextSnapshot = await ruleResearchData.run(request);
    setRuleStatusMessage(
      nextSnapshot === null
        ? "规则回测未完成，请检查参数或下方错误提示。"
        : `规则回测已完成，当前主展示区已切换为 ${selectedRuleHistoryYears} 年约 ${ruleLookbackLimit} 根日线样本。`,
    );
  }

  async function applyExampleAndRun() {
    setRuleMaWindow("60");
    setRuleBuyBelowMaPct("0.05");
    setRuleSellAboveMaPct("0.10");
    setRuleTargetPosition("400");
    const exampleRequest: Partial<ResearchRuleSnapshotRequest> = {
      initialCash: Number(ruleInitialCash),
      ruleConfig: {
        maWindow: 60,
        buyBelowMaPct: 0.05,
        sellAboveMaPct: 0.1,
        targetPosition: 400,
      },
    };
    await runRuleResearch(exampleRequest);
  }

  async function persistAiSettings() {
    const nextApiKey = aiApiKey.trim() ? aiApiKey.trim() : undefined;
    const savedSettings = await aiSettings.save({
      provider: aiProvider,
      model: aiModel,
      baseUrl: aiBaseUrl,
      apiKey: nextApiKey,
      clearApiKey: clearSavedApiKey,
    });
    if (savedSettings !== null) {
      setAiApiKey("");
      setClearSavedApiKey(false);
      setSettingsMessage("AI 配置已保存到后端。");
    }
    return savedSettings;
  }

  async function saveAndRunAiBacktest() {
    const savedSettings = await persistAiSettings();
    if (savedSettings === null) {
      return;
    }
    setSettingsMessage(
      `AI 配置已保存，开始运行最近 ${DEFAULT_AI_RESEARCH_PREVIEW_LIMIT} 根 K 线的快速回测。`,
    );
    const nextSnapshot = await aiResearchData.run({
      symbol: selectedSymbol,
      timeframe: selectedTimeframe,
      limit: DEFAULT_AI_RESEARCH_PREVIEW_LIMIT,
      provider: savedSettings.provider,
      model: savedSettings.model,
      baseUrl: savedSettings.baseUrl,
    });
    setSettingsMessage(
      nextSnapshot === null
        ? "AI 回测未完成，请检查下方错误提示。"
        : `AI 回测已完成，当前展示最近 ${DEFAULT_AI_RESEARCH_PREVIEW_LIMIT} 根 K 线的快速预览。`,
    );
  }

  function renderSnapshotSections(
    nextSnapshot: ResearchSnapshot | null,
    {
      isLoading,
      error,
      metadataItems,
      options,
    }: {
      isLoading: boolean;
      error: string | null;
      metadataItems: ReturnType<typeof buildMetadataItems>;
      options: SnapshotSectionOptions;
    },
  ) {
    const performance = nextSnapshot?.performance;
    const equityCurve = nextSnapshot?.equityCurve ?? [];
    const decisions = nextSnapshot?.decisions ?? [];
    const segments = nextSnapshot?.segments ?? [];
    const notes = nextSnapshot?.notes ?? [];
    const nextManifest = nextSnapshot?.manifest;
    const sampleInfo = nextSnapshot?.sample;
    const strategyItems = buildStrategyItems(nextSnapshot, {
      isLoading,
      error,
      waitingHint: "回测结果返回后，这里会把当前策略的说明、逻辑和参数展开。",
    });

    return (
      <>
        <section className="metric-grid">
          <MetricCard
            label={`${options.labelPrefix}这次赚亏`}
            value={formatSignedMoney(performance?.netPnl)}
            hint={
              performance
                ? `收益率 ${formatDecimal(performance.totalReturnPct, 4)}%`
                : "等待回测结果。"
            }
            tone={performance !== undefined && performance.netPnl >= 0 ? "positive" : "default"}
          />
          <MetricCard
            label={`${options.labelPrefix}中途最大回落`}
            value={performance ? `${formatDecimal(performance.maxDrawdownPct, 4)}%` : "--"}
            hint={performance ? "回测过程中从高点回落最多的一次" : "等待回测结果。"}
            tone="warning"
          />
          <MetricCard
            label={`${options.labelPrefix}完成交易数`}
            value={performance?.tradeCount ?? "--"}
            hint={
              performance
                ? `${performance.fillCount} 笔成交 / ${performance.signalCount} 个信号`
                : "等待回测结果。"
            }
            tone="default"
          />
          <MetricCard
            label={`${options.labelPrefix}结束时账户资金`}
            value={formatDecimal(performance?.endingEquity, 2)}
            hint={
              performance
                ? `期初 ${formatDecimal(performance.startingEquity, 2)}`
                : "等待回测结果。"
            }
            tone="default"
          />
        </section>

        <section className="metric-grid">
          <MetricCard
            label={`${options.labelPrefix}Sharpe`}
            value={formatRatioMetric(performance?.sharpeRatio)}
            hint={
              performance?.sharpeRatio !== undefined
                ? "按 bar 收益波动调整后的收益表现，越高越稳。"
                : "等待回测结果。"
            }
            tone="default"
          />
          <MetricCard
            label={`${options.labelPrefix}收益回撤比`}
            value={formatRatioMetric(performance?.returnToDrawdownRatio)}
            hint={
              performance?.returnToDrawdownRatio !== undefined
                ? "同样的收益如果伴随更小回撤，这个值会更高。"
                : "等待回测结果。"
            }
            tone="default"
          />
          <MetricCard
            label={`${options.labelPrefix}平均持有周期`}
            value={formatAverageHoldingBars(performance?.avgHoldingBars)}
            hint={
              performance?.avgHoldingBars !== undefined
                ? "按已完成卖出数量折算的平均持仓 bar 数。"
                : "等待回测结果。"
            }
            tone="default"
          />
          <MetricCard
            label={`${options.labelPrefix}平均单笔盈亏`}
            value={formatSignedMoney(performance?.avgTradePnl)}
            hint={
              performance?.avgTradePnl !== undefined
                ? `盈利均值 ${formatSignedMoney(performance?.avgWinningTradePnl)} / 亏损均值 ${formatSignedMoney(performance?.avgLosingTradePnl)}`
                : "等待回测结果。"
            }
            tone={
              performance?.avgTradePnl !== undefined &&
              performance?.avgTradePnl !== null &&
              performance.avgTradePnl > 0
                ? "positive"
                : "default"
            }
          />
        </section>

        <section className="page-grid">
          <div className="page-grid__main">
            <SectionCard
              eyebrow={options.eyebrow}
              title={options.chartTitle}
              description={options.chartDescription}
            >
              {error ? <p className="section-error">{error}</p> : null}
              {equityCurve.length > 0 && nextManifest !== undefined ? (
                <AreaChart
                  title={options.chartTitle}
                  subtitle={`${formatSymbolList(nextManifest.symbols, symbolNames)} · ${nextManifest.timeframe} · ${nextManifest.barCount} 根 K 线`}
                  points={equityCurve}
                  accent={options.chartAccent}
                  formatAsMoney
                />
              ) : (
                <div className="empty-state">
                  <p className="empty-state__title">
                    {isLoading ? "正在生成回测结果" : options.emptyTitle}
                  </p>
                  <p className="empty-state__copy">
                    {error ? "当前请求失败，可稍后重试或调整参数后再试。" : options.emptyCopy}
                  </p>
                </div>
              )}
            </SectionCard>

            <SectionCard
              eyebrow={options.decisionEyebrow}
              title={options.decisionTitle}
              description={options.decisionDescription}
            >
              {decisions.length > 0 ? (
                <BacktestDecisionTable decisions={decisions} />
              ) : (
                <div className="empty-state">
                  <p className="empty-state__title">还没有决策记录</p>
                  <p className="empty-state__copy">
                    生成回测结果后，这里会展示每一步的信号和下单计划。
                  </p>
                </div>
              )}
            </SectionCard>

            <SectionCard
              eyebrow="时间分段"
              title={`${options.labelPrefix}不同阶段表现对比`}
              description="把当前样本按时间切成多段，观察策略是否只在某一小段行情里偶然有效。"
            >
              {segments.length > 0 ? (
                <div className="definition-grid">
                  {segments.map((segment) => (
                    <div
                      key={`${segment.label}-${segment.startTime}`}
                      className="definition-grid__item"
                    >
                      <strong>
                        {segment.label} · {segment.marketRegimeLabel}
                      </strong>
                      <p>
                        {formatDateTime(segment.startTime)} 至 {formatDateTime(segment.endTime)}
                      </p>
                      <p>
                        {segment.barCount} 根 K 线 / 价格变化 {formatDecimal(segment.priceChangePct, 4)}%
                      </p>
                      <p>
                        收益 {formatSignedMoney(segment.performance.netPnl)} / 最大回撤{" "}
                        {formatDecimal(segment.performance.maxDrawdownPct, 4)}% / 交易{" "}
                        {segment.performance.tradeCount} 次
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <p className="empty-state__title">当前还没有时间分段对比</p>
                  <p className="empty-state__copy">
                    {sampleInfo?.warning ??
                      "切到评估样本后，这里会展示不同时间窗口的收益、回撤和交易次数差异。"}
                  </p>
                </div>
              )}
            </SectionCard>
          </div>

          <aside className="page-grid__rail">
            <SectionCard
              eyebrow={options.strategyEyebrow}
              title={options.strategyTitle}
              description={options.strategyDescription}
            >
              <DefinitionGrid items={strategyItems} />
            </SectionCard>

            <SectionCard
              eyebrow={options.metadataEyebrow}
              title={options.metadataTitle}
              description={options.metadataDescription}
            >
              <DefinitionGrid items={metadataItems} />
            </SectionCard>

            <SectionCard
              eyebrow={options.notesEyebrow}
              title={options.notesTitle}
              description={options.notesDescription}
            >
              {notes.length > 0 ? (
                <ul className="note-list">
                  {notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              ) : (
                <div className="empty-state">
                  <p className="empty-state__title">等待说明内容</p>
                  <p className="empty-state__copy">
                    回测结果返回后，这里会展示当前回放来源和页面说明。
                  </p>
                </div>
              )}
            </SectionCard>
          </aside>
        </section>
      </>
    );
  }

  return (
    <main className="page-stack">
      <section className="page-hero">
        <div className="page-hero__copy">
          <p className="page-hero__eyebrow">策略回看</p>
          <h2 className="page-hero__title">回测结果一眼看懂</h2>
          <p className="page-hero__summary">
            这里会按你选中的标的和周期，统一生成基线研究结果，并根据模式补上参数扫描、滚动评估或 AI 对照，让你先看结论，再看原因。
          </p>
          <DatasetSwitcher
            symbolOptions={availableSymbols.map((value) => ({
              value,
              label: formatSymbolLabel(value, symbolNames),
            }))}
            timeframeOptions={availableTimeframes.map((value) => ({ value }))}
            symbol={selectedSymbol}
            timeframe={selectedTimeframe}
            onSymbolChange={onSymbolChange}
            onTimeframeChange={onTimeframeChange}
          />

          <div className="dataset-switcher__group">
            <p className="dataset-switcher__label">研究模式</p>
            <div className="dataset-switcher__options">
              <button
                type="button"
                className={`dataset-switcher__button${
                  selectedMode === "evaluation" ? " dataset-switcher__button--active" : ""
                }`}
                onClick={() => onModeChange("evaluation")}
              >
                评估样本 {DEFAULT_RESEARCH_EVALUATION_LIMIT} 根
              </button>
              <button
                type="button"
                className={`dataset-switcher__button${
                  selectedMode === "preview" ? " dataset-switcher__button--active" : ""
                }`}
                onClick={() => onModeChange("preview")}
              >
                快速预览 {DEFAULT_RESEARCH_PREVIEW_LIMIT} 根
              </button>
              <button
                type="button"
                className={`dataset-switcher__button${
                  selectedMode === "parameter_scan" ? " dataset-switcher__button--active" : ""
                }`}
                onClick={() => onModeChange("parameter_scan")}
              >
                参数扫描
              </button>
              <button
                type="button"
                className={`dataset-switcher__button${
                  selectedMode === "walk_forward" ? " dataset-switcher__button--active" : ""
                }`}
                onClick={() => onModeChange("walk_forward")}
              >
                滚动评估
              </button>
            </div>
            <p className="field__hint">{buildResearchModeCopy(selectedMode)}</p>
          </div>

          <div className="dataset-switcher__group">
            <p className="dataset-switcher__label">规则回测样本</p>
            <div className="dataset-switcher__options">
              {RULE_RESEARCH_HISTORY_YEAR_OPTIONS.map((years) => (
                <button
                  key={years}
                  type="button"
                  className={`dataset-switcher__button${
                    selectedRuleHistoryYears === years ? " dataset-switcher__button--active" : ""
                  }`}
                  onClick={() => onRuleHistoryYearsChange(years)}
                >
                  {years} 年
                </button>
              ))}
            </div>
            <p className="field__hint">
              规则回测会复用上方股票代码，推荐切到 `1d` 日线；当前 {selectedRuleHistoryYears} 年约{" "}
              {ruleLookbackLimit} 根 bar，后续会直接映射到规则回测请求的 `limit`。
            </p>
          </div>
        </div>
        <div className="page-hero__chips">
          <span className={`tag${sourceIsFixture ? " tag--fixture" : ""}`}>{sourceLabel}</span>
          {summary ? <span className="tag">{summary.modeLabel}</span> : null}
          {sample !== undefined && sample !== null ? (
            <span className="tag">{`${sample.label} · ${sample.actualBarCount} 根`}</span>
          ) : null}
          <span className="tag">{formatSymbolLabel(selectedSymbol, symbolNames)}</span>
          <span className="tag">{manifest?.strategyId ?? "baseline_momentum_v1"}</span>
          <span className="tag">{manifest?.timeframe ?? selectedTimeframe}</span>
        </div>
      </section>

      {renderSnapshotSections(primarySnapshot, {
        isLoading:
          ruleResearchData.snapshot !== null ? ruleResearchData.isLoading : researchData.isLoading,
        error: ruleResearchData.snapshot !== null ? ruleResearchData.error : researchData.error,
        metadataItems: primaryMetadataItems,
        options: {
          labelPrefix: "",
          eyebrow: "资金变化",
          chartTitle: "账户资金变化",
          chartDescription: "看选中标的在这次回测里的账户资金变化。",
          chartAccent: "red",
          strategyEyebrow: "当前策略",
          strategyTitle: "这次回测怎么判断买卖",
          strategyDescription: "把当前策略的中文说明、核心逻辑和关键参数放到同一个卡片里看。",
          decisionEyebrow: "买卖原因",
          decisionTitle: "每一步为什么买卖",
          decisionDescription: "按时间列出信号、策略动作和下单计划。",
          metadataEyebrow: "回测信息",
          metadataTitle: "本次回放信息",
          metadataDescription: "这次回测用的时间范围、标的和成本假设。",
          notesEyebrow: "数据说明",
          notesTitle: "这页数据从哪来",
          notesDescription: "说明当前展示的数据来源和接入方式。",
          emptyTitle: "暂无回测结果",
          emptyCopy: "切换到这里后，页面会基于真实历史价格即时生成一份回测结果。",
        },
      })}

      <SectionCard
        eyebrow="规则回测"
        title="前端直接配置均线规则"
        description="不需要改 YAML 或后端参数，直接在这里配置 MA、买卖阈值、目标仓位和样本区间。"
      >
        <form
          className="rule-form"
          onSubmit={(event) => {
            event.preventDefault();
            void runRuleResearch();
          }}
        >
          {ruleResearchData.error ? <p className="section-error">{ruleResearchData.error}</p> : null}
          {ruleStatusMessage ? <p className="section-success">{ruleStatusMessage}</p> : null}

          <div className="rule-form__summary">
            <div className="page-hero__chips page-hero__chips--left">
              <span className="tag">{formatSymbolLabel(selectedSymbol, symbolNames)}</span>
              <span className="tag">固定周期 {DEFAULT_RULE_RESEARCH_TIMEFRAME}</span>
              <span className="tag">{selectedRuleHistoryYears} 年 / 约 {ruleLookbackLimit} 根</span>
              <span className="tag">模板 {DEFAULT_RULE_RESEARCH_TEMPLATE}</span>
            </div>
            <p className="field__hint">
              股票代码直接跟随研究页顶部 selector；第一版规则回测固定使用 `1d` 日线，并把上面选择的样本区间换算成请求里的 `limit`。
            </p>
          </div>

          <div className="rule-form__grid">
            <label className="field">
              <span className="field__label">均线周期</span>
              <input
                type="number"
                min="2"
                step="1"
                value={ruleMaWindow}
                onChange={(event) => setRuleMaWindow(event.target.value)}
                className="field__control"
              />
              <span className="field__hint">例如 60，表示 MA60，也就是最近 60 根日线的均值。</span>
            </label>

            <label className="field">
              <span className="field__label">低于均线买入比例</span>
              <input
                type="number"
                min="0"
                max="0.99"
                step="0.01"
                value={ruleBuyBelowMaPct}
                onChange={(event) => setRuleBuyBelowMaPct(event.target.value)}
                className="field__control"
              />
              <span className="field__hint">
                填 0.05 表示收盘价低于 MA 5% 才买入。
              </span>
            </label>

            <label className="field">
              <span className="field__label">高于均线卖出比例</span>
              <input
                type="number"
                min="0"
                max="0.99"
                step="0.01"
                value={ruleSellAboveMaPct}
                onChange={(event) => setRuleSellAboveMaPct(event.target.value)}
                className="field__control"
              />
              <span className="field__hint">
                填 0.10 表示收盘价高于 MA 10% 才卖出。
              </span>
            </label>

            <label className="field">
              <span className="field__label">目标仓位</span>
              <input
                type="number"
                min="1"
                step="1"
                value={ruleTargetPosition}
                onChange={(event) => setRuleTargetPosition(event.target.value)}
                className="field__control"
              />
              <span className="field__hint">
                继续沿用系统当前语义，这里填的是目标持仓股数，不是资金占比。
              </span>
            </label>

            <label className="field field--wide">
              <span className="field__label">初始资金</span>
              <input
                type="number"
                min="1"
                step="1000"
                value={ruleInitialCash}
                onChange={(event) => setRuleInitialCash(event.target.value)}
                className="field__control"
              />
              <span className="field__hint">
                用来定义本次回测的起始账户资金，默认 100000。
              </span>
            </label>
          </div>

          <div className="rule-form__footer">
            <div className="rule-form__actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  void applyExampleAndRun();
                }}
                disabled={ruleResearchData.isLoading}
              >
                快速填充示例并运行
              </button>
              <button
                type="submit"
                className="filter-form__button filter-form__button--primary"
                disabled={ruleResearchData.isLoading}
              >
                {ruleResearchData.isLoading ? "规则回测运行中..." : "运行规则回测"}
              </button>
            </div>
            <p className="field__hint">
              示例会直接填入 MA60 / 买入 -5% / 卖出 +10% / 目标仓位 400，并立刻发起回测。
            </p>
          </div>
        </form>
      </SectionCard>

      {summary !== undefined ? (
        <SectionCard
          eyebrow="研究结论"
          title="这次结果先看什么"
          description="把当前模式、样本可信度和关键比较结论收口成最先可读的一层。"
        >
          <section className="metric-grid">
            <MetricCard
              label="当前模式"
              value={summary.modeLabel}
              hint={summary.sampleMessage}
              tone="default"
            />
            <MetricCard
              label="结果摘要"
              value={summary.resultHeadline}
              hint={summary.comparisonMessage ?? "当前模式还没有额外的标准化对照摘要。"}
              tone="default"
            />
          </section>
        </SectionCard>
      ) : null}

      {experiments?.parameterScan || experiments?.walkForward ? (
        <SectionCard
          eyebrow="实验摘要"
          title="Phase 4 标准化实验结果"
          description="参数扫描和滚动评估都会在同一套样本与指标语义下输出，减少人工再加工。"
        >
          <div className="definition-grid">
            {experiments.parameterScan ? (
              <div className="definition-grid__item">
                <strong>参数扫描</strong>
                <p>{`共 ${experiments.parameterScan.combinationCount} 组组合`}</p>
                <p>{`当前最佳：${experiments.parameterScan.bestVariantLabel ?? "暂无"}`}</p>
                <p>
                  {experiments.parameterScan.bestVariant
                    ? `相对 baseline 净收益变化 ${formatSignedMoney(experiments.parameterScan.bestVariant.versusBaseline.netPnlDelta)}`
                    : "当前还没有最佳参数组合。"}
                </p>
              </div>
            ) : null}
            {experiments.walkForward ? (
              <div className="definition-grid__item">
                <strong>滚动评估</strong>
                <p>{`窗口 ${experiments.walkForward.windowBars} 根 / 步长 ${experiments.walkForward.stepBars} 根`}</p>
                <p>{`窗口数 ${experiments.walkForward.windowCount} / 正收益窗口 ${experiments.walkForward.positiveWindowCount}`}</p>
                <p>{`当前最佳窗口：${experiments.walkForward.bestWindowLabel ?? "暂无"}`}</p>
              </div>
            ) : null}
          </div>
        </SectionCard>
      ) : null}

      {comparison !== null ? (
        <SectionCard
          eyebrow="标准化对照"
          title={`${comparison.baselineLabel} vs ${comparison.candidateLabel}`}
          description="把 baseline 与 candidate 放在同一套样本和指标下比较，减少来回切换和人工抄数。"
        >
          <section className="metric-grid">
            <MetricCard
              label="Candidate 相对基线收益"
              value={formatSignedMoney(comparison.netPnlDelta)}
              hint="正值表示 candidate 这次比 baseline 更赚钱。"
              tone={comparison.netPnlDelta >= 0 ? "positive" : "warning"}
            />
            <MetricCard
              label="Candidate 相对基线回撤"
              value={`${formatDecimal(comparison.maxDrawdownDeltaPct, 4)}%`}
              hint="负值表示 candidate 的最大回撤更小。"
              tone={comparison.maxDrawdownDeltaPct <= 0 ? "positive" : "warning"}
            />
            <MetricCard
              label="Candidate 相对基线交易数"
              value={formatSignedCount(comparison.tradeCountDelta)}
              hint="帮助判断收益变化是否只是更频繁交易带来的。"
              tone="default"
            />
            <MetricCard
              label="关键决策差异"
              value={comparison.decisionDiffCount}
              hint="按同一 barKey 比较动作和执行方向是否不同。"
              tone="default"
            />
          </section>

          {comparison.decisionDiffs.length > 0 ? (
            <div className="definition-grid">
              {comparison.decisionDiffs.slice(0, 6).map((diff) => (
                <div key={diff.barKey} className="definition-grid__item">
                  <strong>{formatDateTime(diff.eventTime)}</strong>
                  <p>{`Baseline ${diff.baselineAction} / Candidate ${diff.candidateAction}`}</p>
                  <p>{`Baseline: ${localizeResearchReason(diff.baselineReason) || "无"}`}</p>
                  <p>{`Candidate: ${localizeResearchReason(diff.candidateReason) || "无"}`}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <p className="empty-state__title">当前还没有明显决策分歧</p>
              <p className="empty-state__copy">
                当 baseline 和 candidate 在同一根 K 线上的动作不同，这里会列出关键差异。
              </p>
            </div>
          )}
        </SectionCard>
      ) : null}

      <SectionCard
        eyebrow="AI 回测"
        title="模型实验台"
        description={`数据库里会持久化保存 AI 回测配置，进入研究页时自动回填；运行回测时会优先复用后端已保存的 API Key。为保证交互速度，页面默认只预览最近 ${DEFAULT_AI_RESEARCH_PREVIEW_LIMIT} 根 K 线。`}
      >
        <form
          className="ai-form"
          onSubmit={(event) => {
            event.preventDefault();
            void saveAndRunAiBacktest();
          }}
        >
          {aiSettings.error ? <p className="section-error">{aiSettings.error}</p> : null}
          {settingsMessage ? <p className="section-success">{settingsMessage}</p> : null}

          <div className="ai-form__grid">
            <label className="field">
              <span className="field__label">接入方式</span>
              <select
                value={aiProvider}
                onChange={(event) => {
                  setAiProvider(event.target.value as ResearchAiProvider);
                  aiResearchData.reset();
                }}
                className="field__control"
              >
                <option value="openai_compatible">OpenAI Compatible</option>
                <option value="heuristic_stub">内置 Heuristic Stub</option>
              </select>
              <span className="field__hint">
                OpenAI Compatible 允许你接入 OpenAI 或兼容 Chat Completions 的模型服务。
              </span>
            </label>

            <label className="field">
              <span className="field__label">模型名</span>
              <input
                type="text"
                list="ai-model-suggestions"
                value={aiModel}
                onChange={(event) => setAiModel(event.target.value)}
                className="field__control"
                placeholder="例如 gpt-5.4"
                disabled={aiProvider !== "openai_compatible"}
              />
              <span className="field__hint">支持直接填写自定义模型 ID。</span>
            </label>

            <label className="field field--wide">
              <span className="field__label">Base URL</span>
              <input
                type="text"
                value={aiBaseUrl}
                onChange={(event) => setAiBaseUrl(event.target.value)}
                className="field__control"
                placeholder="https://api.openai.com/v1"
                disabled={aiProvider !== "openai_compatible"}
              />
              <span className="field__hint">
                这里填服务根地址，后端会自动拼到 Chat Completions endpoint。
              </span>
            </label>

            <label className="field field--wide">
              <span className="field__label">API Key</span>
              <input
                type="password"
                value={aiApiKey}
                onChange={(event) => setAiApiKey(event.target.value)}
                className="field__control"
                placeholder="sk-..."
                autoComplete="off"
                disabled={aiProvider !== "openai_compatible"}
              />
              <span className="field__hint">
                {aiProvider !== "openai_compatible"
                  ? "当前选择的是内置 heuristic stub，不会使用外部 API Key。"
                  : savedApiKeyHint && !clearSavedApiKey
                    ? `数据库里已保存 API Key：${savedApiKeyHint}。留空表示继续使用已保存值。`
                    : "输入新 API Key 后保存，会写入后端数据库供后续回测复用。"}
              </span>
            </label>
          </div>

          <datalist id="ai-model-suggestions">
            <option value="gpt-5.4" />
            <option value="gpt-5.2" />
            <option value="gpt-4.1" />
          </datalist>

          <div className="ai-form__footer">
            <div className="ai-form__meta">
              <div className="page-hero__chips page-hero__chips--left">
                <span className="tag">
                  {aiProvider === "openai_compatible" ? "OpenAI Compatible" : "Heuristic Stub"}
                </span>
                <span className="tag">{formatSymbolLabel(selectedSymbol, symbolNames)}</span>
                <span className="tag">{selectedTimeframe}</span>
                {aiResearchData.snapshot?.manifest !== undefined ? (
                  <span className="tag">{aiResearchData.snapshot.manifest.strategyId}</span>
                ) : null}
                {latestAiSettingsUpdatedAt ? (
                  <span className="tag">已保存于 {formatDateTime(latestAiSettingsUpdatedAt)}</span>
                ) : null}
              </div>

              <div className="ai-form__subactions">
                {savedApiKeyHint ? (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => {
                      setClearSavedApiKey(true);
                      setAiApiKey("");
                      setSettingsMessage("当前会在下次保存时清除后端已保存的 API Key。");
                    }}
                    disabled={aiSettings.isSaving || aiResearchData.isLoading}
                  >
                    清除已保存 Key
                  </button>
                ) : null}
              </div>
            </div>

            <div className="ai-form__actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  void persistAiSettings();
                }}
                disabled={aiSettings.isSaving || aiResearchData.isLoading}
              >
                {aiSettings.isSaving ? "保存中..." : "保存 AI 配置"}
              </button>

              <span className="tag">
                {clearSavedApiKey
                  ? "将清除已保存 Key"
                  : `快速预览最近 ${DEFAULT_AI_RESEARCH_PREVIEW_LIMIT} 根 K 线`}
              </span>

              <button
                type="submit"
                className="refresh-button"
                disabled={aiResearchData.isLoading || aiSettings.isSaving || aiSettings.isLoading}
              >
                {aiResearchData.isLoading ? "AI 回测运行中..." : "保存并运行 AI 回测"}
              </button>
            </div>
          </div>
        </form>
      </SectionCard>

      {renderSnapshotSections(aiResearchData.snapshot, {
        isLoading: aiResearchData.isLoading,
        error: aiResearchData.error,
        metadataItems: aiMetadataItems,
        options: {
          labelPrefix: "AI ",
          eyebrow: "AI 资金变化",
          chartTitle: "AI 账户资金变化",
          chartDescription: "看选中标的在这次 AI 回测里的账户资金变化。",
          chartAccent: "teal",
          strategyEyebrow: "AI 策略",
          strategyTitle: "这次 AI 回测怎么判断买卖",
          strategyDescription: "把当前 AI 策略的中文说明、决策逻辑和关键参数直接展开。",
          decisionEyebrow: "AI 买卖原因",
          decisionTitle: "AI 每一步为什么买卖",
          decisionDescription: "按时间列出 AI 信号、策略动作和下单计划。",
          metadataEyebrow: "AI 回测信息",
          metadataTitle: "本次 AI 回放信息",
          metadataDescription: "这次 AI 回测使用的模型、时间范围、标的和成本假设。",
          notesEyebrow: "AI 数据说明",
          notesTitle: "AI 结果从哪来",
          notesDescription: "说明当前 AI 回放的数据来源和模型接入方式。",
          emptyTitle: "还没有 AI 回测结果",
          emptyCopy: "填好并保存模型配置后，点击运行 AI 回测即可生成对照结果。",
        },
      })}
    </main>
  );
}
