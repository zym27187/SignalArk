import {
  compactId,
  formatDateTime,
  formatSymbolLabel,
  summarizePayload,
  titleCase,
} from "../lib/format";
import type { ReplayEvent, SymbolNameMap } from "../types/api";

interface EventTimelineProps {
  events: ReplayEvent[];
  symbolNames: SymbolNameMap;
  error?: string;
}

export function EventTimeline({ events, symbolNames, error }: EventTimelineProps) {
  return (
    <div className="event-timeline">
      {error ? <p className="section-error">事件读取失败：{error}</p> : null}

      {events.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state__title">还没有关键事件</p>
          <p className="empty-state__copy">
            当交易系统开始产出事件后，这里会按时间顺序列出最近发生的事情。
          </p>
        </div>
      ) : (
        <ol className="event-list">
          {events.map((event) => (
            <li
              key={event.event_id}
              className="event-list__item"
            >
              <div className="event-list__header">
                <strong>{titleCase(event.event_type)}</strong>
                <span>{formatDateTime(event.event_time)}</span>
              </div>
              <p className="event-list__meta">
                来源 {event.source} · {formatSymbolLabel(event.symbol, symbolNames, "账户")} · 批次 {compactId(event.trader_run_id)}
              </p>
              {event.reason_code ? (
                <p className="event-list__meta">原因分类：{titleCase(event.reason_code)}</p>
              ) : null}
              <p className="event-list__payload">{summarizePayload(event.payload_json)}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
