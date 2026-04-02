import { compactId, formatDateTime, summarizePayload, titleCase } from "../lib/format";
import type { ReplayEvent } from "../types/api";

interface EventTimelineProps {
  events: ReplayEvent[];
  error?: string;
}

export function EventTimeline({ events, error }: EventTimelineProps) {
  return (
    <div className="event-timeline">
      {error ? <p className="section-error">事件流异常：{error}</p> : null}

      {events.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state__title">暂无回放事件</p>
          <p className="empty-state__copy">
            交易运行时开始产出审计事件后，这里会形成一条便于值守查看的时间线。
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
                {event.source} · {event.symbol ?? "账户范围"} · 运行 {compactId(event.trader_run_id)}
              </p>
              <p className="event-list__payload">{summarizePayload(event.payload_json)}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
