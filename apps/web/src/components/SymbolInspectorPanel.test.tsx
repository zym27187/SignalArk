import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SymbolInspectorPanel } from "./SymbolInspectorPanel";
import { inspectSymbol, submitRuntimeSymbolRequest } from "../lib/api";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual("../lib/api");
  return {
    ...actual,
    inspectSymbol: vi.fn(),
    submitRuntimeSymbolRequest: vi.fn(),
  };
});

const mockedInspectSymbol = vi.mocked(inspectSymbol);
const mockedSubmitRuntimeSymbolRequest = vi.mocked(submitRuntimeSymbolRequest);

describe("SymbolInspectorPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("inspects a symbol and records a runtime change request", async () => {
    mockedInspectSymbol
      .mockResolvedValueOnce({
        raw_input: "000001.sz",
        normalized_symbol: "000001.SZ",
        format_valid: true,
        market: "a_share",
        market_label: "A 股",
        venue: "SZ",
        venue_label: "深圳证券交易所",
        display_name: "平安银行",
        name_status: "available",
        layers: {
          observed: true,
          supported: true,
          runtime_enabled: false,
        },
        reason_code: "SYMBOL_SUPPORTED_NOT_RUNTIME",
        message: "该股票代码已被系统支持，但当前还没有进入 trader 运行范围。",
        runtime_activation: {
          requires_confirmation: true,
          phase: "phase_2_runtime_request",
          can_apply_now: true,
          effective_scope: "runtime_symbols",
          activation_mode: "requires_reload",
          request_status: "not_requested",
          last_requested_at: null,
          requested_runtime_symbols_preview: ["600036.SH", "000001.SZ"],
          message: "确认后可以记录运行范围变更请求，但需要重载 trader 才会真正生效。",
        },
      })
      .mockResolvedValueOnce({
        raw_input: "000001.SZ",
        normalized_symbol: "000001.SZ",
        format_valid: true,
        market: "a_share",
        market_label: "A 股",
        venue: "SZ",
        venue_label: "深圳证券交易所",
        display_name: "平安银行",
        name_status: "available",
        layers: {
          observed: true,
          supported: true,
          runtime_enabled: false,
        },
        reason_code: "SYMBOL_SUPPORTED_NOT_RUNTIME",
        message: "该股票代码已被系统支持，但当前还没有进入 trader 运行范围。",
        runtime_activation: {
          requires_confirmation: true,
          phase: "phase_2_runtime_request",
          can_apply_now: false,
          effective_scope: "runtime_symbols",
          activation_mode: "requires_reload",
          request_status: "pending_reload",
          last_requested_at: "2026-04-11T10:10:00+08:00",
          requested_runtime_symbols_preview: ["600036.SH", "000001.SZ"],
          message: "该股票代码的运行范围变更请求已记录，等待 trader 重载后生效。",
        },
      });
    mockedSubmitRuntimeSymbolRequest.mockResolvedValue({
      accepted: true,
      symbol: "000001.SZ",
      normalized_symbol: "000001.SZ",
      control_state: "normal",
      trader_run_id: "run-001",
      instance_id: "instance-A",
      effective_at: "2026-04-11T10:10:00+08:00",
      effective_scope: "runtime_symbols",
      activation_mode: "requires_reload",
      request_status: "pending_reload",
      message: "已记录运行范围变更请求；需要重载 trader 后才会真正进入运行范围。",
      reason_code: "RUNTIME_CHANGE_REQUIRES_RELOAD",
      current_runtime_symbols: ["600036.SH"],
      requested_runtime_symbols: ["600036.SH", "000001.SZ"],
      last_requested_at: "2026-04-11T10:10:00+08:00",
    });

    render(
      <SymbolInspectorPanel
        runtimeSymbols={["600036.SH"]}
        symbolNames={{ "600036.SH": "招商银行", "000001.SZ": "平安银行" }}
      />,
    );

    fireEvent.change(screen.getByLabelText("股票代码"), {
      target: { value: "000001.sz" },
    });
    fireEvent.click(screen.getByRole("button", { name: "检查代码" }));

    await waitFor(() => {
      expect(mockedInspectSymbol).toHaveBeenCalledWith("000001.sz");
    });

    expect(await screen.findByText("000001.SZ")).toBeInTheDocument();
    expect(
      screen.getAllByText("确认后可以记录运行范围变更请求，但需要重载 trader 才会真正生效。"),
    ).toHaveLength(2);

    fireEvent.click(screen.getByLabelText("我确认这会影响下一次 runtime 运行范围"));
    fireEvent.click(screen.getByRole("button", { name: "记录运行范围变更请求" }));

    await waitFor(() => {
      expect(mockedSubmitRuntimeSymbolRequest).toHaveBeenCalledWith({
        symbol: "000001.SZ",
        confirm: true,
      });
    });

    expect(
      await screen.findByText("已记录运行范围变更请求；需要重载 trader 后才会真正进入运行范围。"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("请求后范围：招商银行 (600036.SH), 平安银行 (000001.SZ)"),
    ).toBeInTheDocument();
    expect(screen.getByText("等待重载")).toBeInTheDocument();
  });

  it("shows unsupported symbols as blocked from runtime requests", async () => {
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
        phase: "phase_2_runtime_request",
        can_apply_now: false,
        effective_scope: "runtime_symbols",
        activation_mode: "unavailable",
        request_status: "unsupported_symbol",
        last_requested_at: null,
        requested_runtime_symbols_preview: ["600036.SH"],
        message: "该股票代码尚未进入 supported_symbols，暂时不能申请加入 runtime。",
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
    expect(
      screen.getByText("该股票代码尚未进入 supported_symbols，暂时不能申请加入 runtime。"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "记录运行范围变更请求" })).not.toBeInTheDocument();
  });
});
