import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AreaChart } from "./AreaChart";

describe("AreaChart", () => {
  it("formats money charts with absolute equity and signed delta", () => {
    render(
      <AreaChart
        title="账户资金变化"
        subtitle="招商银行 (600036.SH) · 1d · 250 根 K 线"
        formatAsMoney
        points={[
          {
            time: "2025-04-03T15:00:00+08:00",
            value: 100000,
            baseline: 100000,
          },
          {
            time: "2026-04-15T15:00:00+08:00",
            value: 100320.45,
            baseline: 100000,
          },
        ]}
      />,
    );

    expect(screen.getByText("100,320.45")).toBeInTheDocument();
    expect(screen.getByText("净变化 +320.45")).toBeInTheDocument();
    expect(screen.queryByText("+100,320.45")).not.toBeInTheDocument();
  });
});
