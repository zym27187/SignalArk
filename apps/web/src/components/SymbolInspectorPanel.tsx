import { useState } from "react";

import { inspectSymbol, submitRuntimeSymbolRequest } from "../lib/api";
import { formatSymbolList, localizeMessage, titleCase } from "../lib/format";
import type {
  RuntimeSymbolRequestResponse,
  SymbolInspectionPayload,
  SymbolNameMap,
} from "../types/api";
import { DefinitionGrid } from "./DefinitionGrid";

const ASHARE_SYMBOL_PATTERN = /^\d{6}\.(SH|SZ)$/;

interface SymbolInspectorPanelProps {
  runtimeSymbols: string[];
  symbolNames: SymbolNameMap;
}

function buildFallbackInspection(rawInput: string): SymbolInspectionPayload {
  const normalizedSymbol = rawInput.trim().toUpperCase();
  const formatValid = ASHARE_SYMBOL_PATTERN.test(normalizedSymbol);
  const venue = formatValid ? normalizedSymbol.slice(-2) : null;

  return {
    raw_input: rawInput,
    normalized_symbol: normalizedSymbol,
    format_valid: formatValid,
    market: formatValid ? "a_share" : "unknown",
    market_label: formatValid ? "A 股" : "待确认",
    venue,
    venue_label: venue === "SH" ? "上海证券交易所" : venue === "SZ" ? "深圳证券交易所" : "待确认",
    display_name: null,
    name_status: "missing",
    layers: {
      observed: Boolean(normalizedSymbol),
      supported: false,
      runtime_enabled: false,
    },
    reason_code: formatValid ? "SYMBOL_OBSERVED_ONLY" : "INVALID_SYMBOL_FORMAT",
    message: formatValid
      ? "系统层状态暂时未确认，当前先按观察层处理。"
      : "代码格式不符合 A 股约定，请使用 6 位数字加 .SH 或 .SZ 后缀。",
    runtime_activation: {
      requires_confirmation: true,
      phase: "phase_2_runtime_request",
      can_apply_now: false,
      effective_scope: "runtime_symbols",
      activation_mode: "unavailable",
      request_status: "invalid_symbol",
      last_requested_at: null,
      requested_runtime_symbols_preview: [],
      message: "代码格式不合法，暂时不能进入 runtime 范围申请。",
    },
  };
}

function describeLayerStatus(inspection: SymbolInspectionPayload): string {
  if (inspection.layers.runtime_enabled) {
    return "已进入当前运行范围";
  }
  if (inspection.layers.supported) {
    return "系统已支持，但未进入当前运行范围";
  }
  if (inspection.layers.observed) {
    return "当前只在观察层";
  }
  return "尚未检查";
}

function describeNameHint(inspection: SymbolInspectionPayload): string {
  if (inspection.name_status === "available") {
    return "系统已经有可直接展示给用户的股票名称。";
  }
  return "名称暂缺，后续需要补充显示名称。";
}

function layerTone(active: boolean): string {
  return active ? "symbol-inspector__layer--active" : "symbol-inspector__layer--inactive";
}

export function SymbolInspectorPanel({
  runtimeSymbols,
  symbolNames,
}: SymbolInspectorPanelProps) {
  const [draft, setDraft] = useState("");
  const [inspection, setInspection] = useState<SymbolInspectionPayload | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRequestingRuntime, setIsRequestingRuntime] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runtimeImpactAcknowledged, setRuntimeImpactAcknowledged] = useState(false);
  const [requestResult, setRequestResult] = useState<RuntimeSymbolRequestResponse | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!draft.trim()) {
      setInspection(null);
      setError("请先输入想检查的股票代码。");
      setRuntimeImpactAcknowledged(false);
      setRequestResult(null);
      return;
    }

    setIsSubmitting(true);
    setRuntimeImpactAcknowledged(false);
    setRequestResult(null);
    try {
      const nextInspection = await inspectSymbol(draft);
      setInspection(nextInspection);
      setError(null);
    } catch (inspectError) {
      setInspection(buildFallbackInspection(draft));
      const message =
        inspectError instanceof Error ? inspectError.message : "符号检查暂时失败。";
      setError(`系统层状态暂时未确认：${localizeMessage(message)}`);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRuntimeRequest() {
    if (!inspection) {
      return;
    }

    setIsRequestingRuntime(true);
    try {
      const response = await submitRuntimeSymbolRequest({
        symbol: inspection.normalized_symbol,
        confirm: true,
      });
      setRequestResult(response);
      setError(null);
      setInspection(await inspectSymbol(inspection.normalized_symbol));
    } catch (requestError) {
      const message =
        requestError instanceof Error ? requestError.message : "运行范围请求提交失败。";
      setError(`运行范围请求提交失败：${localizeMessage(message)}`);
    } finally {
      setIsRequestingRuntime(false);
    }
  }

  return (
    <div className="symbol-inspector">
      <p className="symbol-inspector__intro">
        先检查代码格式、市场归属和当前层级，再决定后续是否需要把它纳入系统支持或运行范围。
      </p>
      <p className="symbol-inspector__current-runtime">
        当前运行范围：{formatSymbolList(runtimeSymbols, symbolNames)}
      </p>

      <form className="symbol-inspector__form" onSubmit={handleSubmit}>
        <label className="symbol-inspector__field">
          <span>股票代码</span>
          <input
            type="text"
            value={draft}
            placeholder="例如 600036.SH"
            onChange={(event) => {
              setDraft(event.target.value);
            }}
          />
        </label>
        <button type="submit" className="symbol-inspector__submit" disabled={isSubmitting}>
          {isSubmitting ? "检查中..." : "检查代码"}
        </button>
      </form>

      {error ? <p className="symbol-inspector__error">{error}</p> : null}

      {inspection ? (
        <div className="symbol-inspector__result">
          <div className="symbol-inspector__summary">
            <span className="mini-label">检查结论</span>
            <strong>{inspection.message}</strong>
            <p>
              当前层级：{describeLayerStatus(inspection)}，原因分类：{titleCase(inspection.reason_code)}
            </p>
          </div>

          <div className="symbol-inspector__layers" aria-label="当前层级状态">
            <span className={`symbol-inspector__layer ${layerTone(inspection.layers.observed)}`}>
              观察层
            </span>
            <span className={`symbol-inspector__layer ${layerTone(inspection.layers.supported)}`}>
              支持层
            </span>
            <span
              className={`symbol-inspector__layer ${layerTone(inspection.layers.runtime_enabled)}`}
            >
              运行层
            </span>
          </div>

          <DefinitionGrid
            items={[
              {
                label: "规范化代码",
                value: inspection.normalized_symbol || "--",
                hint: "系统会先把输入统一成大写代码，便于后续比较。",
              },
              {
                label: "股票名称",
                value: inspection.display_name ?? "名称暂缺",
                hint: describeNameHint(inspection),
              },
              {
                label: "市场归属",
                value: `${inspection.market_label} / ${inspection.venue_label}`,
                hint: "这里只判断当前仓库固定支持的 A 股代码格式和市场后缀。",
              },
              {
                label: "格式是否合法",
                value: inspection.format_valid ? "合法" : "需修正",
                hint: inspection.format_valid
                  ? "格式已经满足 A 股代码约定。"
                  : "请使用 6 位数字加 .SH 或 .SZ，例如 600036.SH。",
              },
              {
                label: "当前层级",
                value: describeLayerStatus(inspection),
                hint: "观察层不代表已支持，更不代表已经进入 trader 运行范围。",
              },
            ]}
          />

          {inspection.format_valid ? (
            <div className="symbol-inspector__runtime-request">
              <DefinitionGrid
                items={[
                  {
                    label: "运行范围动作",
                    value: titleCase(inspection.runtime_activation.request_status),
                    hint: inspection.runtime_activation.message,
                  },
                  {
                    label: "影响范围",
                    value: titleCase(inspection.runtime_activation.effective_scope),
                    hint: "这里指的是 trader 的运行标的范围，而不是观察层或系统支持边界。",
                  },
                  {
                    label: "生效方式",
                    value: titleCase(inspection.runtime_activation.activation_mode),
                    hint: inspection.runtime_activation.can_apply_now
                      ? "当前系统会先记录请求，真正进入运行范围仍需要后续重载。"
                      : "当前状态会直接告诉你能不能继续进入 runtime 变更流程。",
                  },
                  {
                    label: "变更后预览",
                    value: formatSymbolList(
                      inspection.runtime_activation.requested_runtime_symbols_preview,
                      symbolNames,
                    ),
                    hint: "这里展示的是提交成功后期望进入的运行标的范围预览。",
                  },
                ]}
              />

              {inspection.runtime_activation.can_apply_now ? (
                <div className="symbol-inspector__confirmation" role="alert">
                  <strong>这一步会记录运行范围变更请求，但不会立即热更新当前 trader。</strong>
                  <p>{inspection.runtime_activation.message}</p>
                  <label className="symbol-inspector__toggle">
                    <input
                      type="checkbox"
                      checked={runtimeImpactAcknowledged}
                      onChange={(event) => {
                        setRuntimeImpactAcknowledged(event.target.checked);
                      }}
                      aria-label="我确认这会影响下一次 runtime 运行范围"
                    />
                    <span>我确认这会影响下一次 runtime 运行范围</span>
                  </label>
                  <button
                    type="button"
                    className="symbol-inspector__acknowledge"
                    onClick={() => {
                      void handleRuntimeRequest();
                    }}
                    disabled={!runtimeImpactAcknowledged || isRequestingRuntime}
                  >
                    {isRequestingRuntime ? "记录中..." : "记录运行范围变更请求"}
                  </button>
                </div>
              ) : null}

              {requestResult ? (
                <div className="symbol-inspector__acknowledged">
                  <strong>{requestResult.message}</strong>
                  <p>
                    当前范围：{formatSymbolList(requestResult.current_runtime_symbols, symbolNames)}
                  </p>
                  <p>
                    请求后范围：{formatSymbolList(requestResult.requested_runtime_symbols, symbolNames)}
                  </p>
                  <p>
                    作用范围：{titleCase(requestResult.effective_scope)}，生效方式：
                    {titleCase(requestResult.activation_mode)}
                  </p>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="symbol-inspector__runtime-blocked">
              代码格式还不合法，暂时不能进入后续运行范围评估。
            </p>
          )}
        </div>
      ) : (
        <div className="symbol-inspector__empty">
          <p className="empty-state__title">还没有检查股票代码</p>
          <p className="empty-state__copy">
            输入一个 A 股代码后，这里会告诉你它现在只是观察对象、已经被系统支持，还是已经进入当前运行范围。
          </p>
        </div>
      )}
    </div>
  );
}
