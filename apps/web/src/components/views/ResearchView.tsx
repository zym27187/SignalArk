import { useEffect, useState } from "react";

import { AreaChart } from "../AreaChart";
import { BacktestDecisionTable } from "../BacktestDecisionTable";
import { DatasetSwitcher } from "../DatasetSwitcher";
import { DefinitionGrid } from "../DefinitionGrid";
import { MetricCard } from "../MetricCard";
import { SectionCard } from "../SectionCard";
import { useAiResearchData } from "../../hooks/use-ai-research-data";
import type { ResearchDataState } from "../../hooks/use-research-data";
import {
  formatDateTime,
  formatDecimal,
  formatSignedMoney,
  formatSymbolLabel,
  formatSymbolList,
} from "../../lib/format";
import type { SymbolNameMap } from "../../types/api";
import type { ResearchAiProvider, ResearchSnapshot } from "../../types/research";

interface ResearchViewProps {
  researchData: ResearchDataState;
  availableSymbols: string[];
  symbolNames: SymbolNameMap;
  availableTimeframes: string[];
  selectedSymbol: string;
  selectedTimeframe: string;
  onSymbolChange: (symbol: string) => void;
  onTimeframeChange: (timeframe: string) => void;
}

interface SnapshotSectionOptions {
  labelPrefix: string;
  eyebrow: string;
  chartTitle: string;
  chartDescription: string;
  chartAccent: "teal" | "amber" | "red";
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
      label: "本次回测编号",
      value: manifest.runId,
      hint: manifest.description,
    },
    {
      label: "回测时间范围",
      value: `${formatDateTime(manifest.startTime)} 至 ${formatDateTime(manifest.endTime)}`,
    },
    {
      label: "账户与标的",
      value: `${manifest.accountId} / ${formatSymbolList(manifest.symbols, symbolNames)}`,
      hint: `${manifest.handlerName} · ${manifest.timeframe}`,
    },
    {
      label: "交易成本假设",
      value: `滑点 ${formatDecimal(manifest.slippageBps, 0)} bps`,
      hint: `${manifest.feeModel} + ${manifest.slippageModel}`,
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

export function ResearchView({
  researchData,
  availableSymbols,
  symbolNames,
  availableTimeframes,
  selectedSymbol,
  selectedTimeframe,
  onSymbolChange,
  onTimeframeChange,
}: ResearchViewProps) {
  const aiResearchData = useAiResearchData();
  const [aiProvider, setAiProvider] = useState<ResearchAiProvider>("openai_compatible");
  const [aiModel, setAiModel] = useState("gpt-5.4");
  const [aiBaseUrl, setAiBaseUrl] = useState("https://api.openai.com/v1");
  const [aiApiKey, setAiApiKey] = useState("");

  useEffect(() => {
    aiResearchData.reset();
  }, [selectedSymbol, selectedTimeframe]);

  const snapshot = researchData.snapshot;
  const manifest = snapshot?.manifest;
  const sourceLabel = snapshot
    ? snapshot.sourceMode === "fixture"
      ? snapshot.sourceLabel
      : "真实回测结果"
    : researchData.isLoading
      ? "正在生成回测结果"
      : "等待回测数据";
  const sourceIsFixture = snapshot?.sourceMode === "fixture";
  const baselineMetadataItems = buildMetadataItems(snapshot, {
    isLoading: researchData.isLoading,
    error: researchData.error,
    symbolNames,
    waitingHint: "选择标的和周期后，这里会生成一份回测结果。",
  });
  const aiMetadataItems = buildMetadataItems(aiResearchData.snapshot, {
    isLoading: aiResearchData.isLoading,
    error: aiResearchData.error,
    symbolNames,
    waitingHint: "填好模型接入信息后，这里会生成一份 AI 回测结果。",
  });

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
    const notes = nextSnapshot?.notes ?? [];
    const nextManifest = nextSnapshot?.manifest;

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
          </div>

          <aside className="page-grid__rail">
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
            这里会按你选中的标的和周期，直接生成一份基线回测结果，再额外接出一块 AI 回测实验区，帮助快速横向比较不同决策方式的收益、回撤和买卖原因。
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
        </div>
        <div className="page-hero__chips">
          <span className={`tag${sourceIsFixture ? " tag--fixture" : ""}`}>{sourceLabel}</span>
          <span className="tag">{formatSymbolLabel(selectedSymbol, symbolNames)}</span>
          <span className="tag">{manifest?.strategyId ?? "baseline_momentum_v1"}</span>
          <span className="tag">{manifest?.timeframe ?? selectedTimeframe}</span>
        </div>
      </section>

      {renderSnapshotSections(snapshot, {
        isLoading: researchData.isLoading,
        error: researchData.error,
        metadataItems: baselineMetadataItems,
        options: {
          labelPrefix: "",
          eyebrow: "资金变化",
          chartTitle: "账户资金变化",
          chartDescription: "看选中标的在这次回测里的账户资金变化。",
          chartAccent: "red",
          decisionEyebrow: "买卖原因",
          decisionTitle: "每一步为什么买卖",
          decisionDescription: "按时间列出信号、动作和下单计划。",
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
        eyebrow="AI 回测"
        title="模型实验台"
        description="接入 OpenAI-compatible 模型，指定模型名和 Base URL，单独生成一份 AI 回测结果。"
      >
        <form
          className="ai-form"
          onSubmit={(event) => {
            event.preventDefault();
            void aiResearchData.run({
              symbol: selectedSymbol,
              timeframe: selectedTimeframe,
              limit: 96,
              provider: aiProvider,
              model: aiProvider === "openai_compatible" ? aiModel : undefined,
              baseUrl: aiProvider === "openai_compatible" ? aiBaseUrl : undefined,
              apiKey: aiProvider === "openai_compatible" ? aiApiKey : undefined,
            });
          }}
        >
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
                仅用于当前这次 AI 回测请求，不会由前端持久化，也不会写回数据库。
              </span>
            </label>
          </div>

          <datalist id="ai-model-suggestions">
            <option value="gpt-5.4" />
            <option value="gpt-5.2" />
            <option value="gpt-4.1" />
          </datalist>

          <div className="ai-form__footer">
            <div className="page-hero__chips page-hero__chips--left">
              <span className="tag">
                {aiProvider === "openai_compatible" ? "OpenAI Compatible" : "Heuristic Stub"}
              </span>
              <span className="tag">{formatSymbolLabel(selectedSymbol, symbolNames)}</span>
              <span className="tag">{selectedTimeframe}</span>
              {aiResearchData.snapshot?.manifest !== undefined ? (
                <span className="tag">{aiResearchData.snapshot.manifest.strategyId}</span>
              ) : null}
            </div>

            <button
              type="submit"
              className="refresh-button"
              disabled={aiResearchData.isLoading}
            >
              {aiResearchData.isLoading ? "AI 回测运行中..." : "运行 AI 回测"}
            </button>
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
          decisionEyebrow: "AI 买卖原因",
          decisionTitle: "AI 每一步为什么买卖",
          decisionDescription: "按时间列出 AI 信号、动作和下单计划。",
          metadataEyebrow: "AI 回测信息",
          metadataTitle: "本次 AI 回放信息",
          metadataDescription: "这次 AI 回测使用的模型、时间范围、标的和成本假设。",
          notesEyebrow: "AI 数据说明",
          notesTitle: "AI 结果从哪来",
          notesDescription: "说明当前 AI 回放的数据来源和模型接入方式。",
          emptyTitle: "还没有 AI 回测结果",
          emptyCopy: "填好模型、Base URL 和 API Key 后，点击运行 AI 回测即可生成对照结果。",
        },
      })}
    </main>
  );
}
