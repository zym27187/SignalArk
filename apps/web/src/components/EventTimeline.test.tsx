import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EventTimeline } from "./EventTimeline";

describe("EventTimeline", () => {
  it("shows replay event reason codes when available", () => {
    render(
      <EventTimeline
        events={[
          {
            event_id: "event-001",
            event_type: "runtime.market_data_stale_repeated",
            source: "trader",
            reason_code: "MARKET_DATA_STALE",
            trader_run_id: "run-001",
            account_id: "paper_account_001",
            exchange: "cn_equity",
            symbol: "600036.SH",
            related_object_type: "runtime",
            event_time: "2026-04-02T10:00:00+08:00",
            ingest_time: "2026-04-02T10:00:00+08:00",
            created_at: "2026-04-02T10:00:00+08:00",
            payload_json: { stale_check_count: 2 },
          },
        ]}
        symbolNames={{ "600036.SH": "招商银行" }}
      />,
    );

    expect(screen.getByText("原因分类：行情过期")).toBeInTheDocument();
  });
});
