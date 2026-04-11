import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SymbolInspectorPanel } from "./SymbolInspectorPanel";
import { inspectSymbol } from "../lib/api";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual("../lib/api");
  return {
    ...actual,
    inspectSymbol: vi.fn(),
  };
});

const mockedInspectSymbol = vi.mocked(inspectSymbol);

describe("SymbolInspectorPanel", () => {
  it("inspects a symbol and explains the runtime request impact", async () => {
    mockedInspectSymbol.mockResolvedValue({
      raw_input: "300750.sz",
      normalized_symbol: "300750.SZ",
      format_valid: true,
      market: "a_share",
      market_label: "A 股",
      venue: "SZ",
      venue_label: "深圳证券交易所",
      display_name: null,
      name_status: "missing",
      layers: {
        observed: true,
        supported: false,
        runtime_enabled: false,
      },
      reason_code: "SYMBOL_OBSERVED_ONLY",
      message: "该股票代码当前只处于观察层，可继续校验或纳入后续支持评估。",
      runtime_activation: {
        requires_confirmation: true,
        phase: "phase_1_preview_only",
        can_apply_now: false,
        message: "当前前端只提供影响说明，不会直接修改 trader 运行范围。",
      },
    });

    render(
      <SymbolInspectorPanel
        runtimeSymbols={["600036.SH"]}
        symbolNames={{ "600036.SH": "招商银行" }}
      />,
    );

    fireEvent.change(screen.getByLabelText("股票代码"), {
      target: { value: "300750.sz" },
    });
    fireEvent.click(screen.getByRole("button", { name: "检查代码" }));

    await waitFor(() => {
      expect(mockedInspectSymbol).toHaveBeenCalledWith("300750.sz");
    });

    expect(await screen.findByText("300750.SZ")).toBeInTheDocument();
    expect(screen.getByText("该股票代码当前只处于观察层，可继续校验或纳入后续支持评估。")).toBeInTheDocument();
    expect(screen.getByText("名称暂缺，后续需要补充显示名称。")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("后续希望把它加入运行范围"));

    expect(
      screen.getByText("当前不会立即生效，也不会立刻修改 trader 的实际交易范围。"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "我已理解影响" }));

    expect(
      screen.getByText("已记录为本次会话中的运行范围申请意向，真正生效需要后续 Phase 2 闭环。"),
    ).toBeInTheDocument();
  });
});
