import { compactId, formatDateTime, summarizePayload, titleCase } from "../lib/format";
import type { ReplayEvent } from "../types/api";

interface EventTimelineProps {
  events: ReplayEvent[];
  error?: string;
}

export function EventTimeline({ events, error }: EventTimelineProps) {
  return (
    <div className="event-timeline">
      {error ? <p className="section-error">Events feed issue: {error}</p> : null}

      {events.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state__title">No replay events loaded</p>
          <p className="empty-state__copy">
            Once the trader emits audit events, this rail becomes a quick operator timeline.
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
                {event.source} · {event.symbol ?? "Account scope"} · Run {compactId(event.trader_run_id)}
              </p>
              <p className="event-list__payload">{summarizePayload(event.payload_json)}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

