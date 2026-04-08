import { compactId, formatDateTime, summarizePayload, titleCase } from "../lib/format";
import type { ReplayEvent } from "../types/api";

interface EventTimelineProps {
  events: ReplayEvent[];
  error?: string;
}

export function EventTimeline({ events, error }: EventTimelineProps) {
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
                来源 {event.source} · {event.symbol ?? "账户"} · 批次 {compactId(event.trader_run_id)}
              </p>
              <p className="event-list__payload">{summarizePayload(event.payload_json)}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
