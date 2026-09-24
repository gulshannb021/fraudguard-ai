import "./CaseTimeline.css";

export default function CaseTimeline({ events = [] }) {
  if (events.length === 0) {
    return <p className="timeline-empty">No timeline events yet.</p>;
  }

  return (
    <ol className="case-timeline">
      {events.map((event, i) => (
        <li key={event.id || i}>
          <div className="timeline-dot" />
          <div className="timeline-content">
            <div className="timeline-label">
              {event.label || event.type || event.title}
            </div>
            {event.timestamp && (
              <div className="timeline-time">
                {new Date(event.timestamp).toLocaleString()}
              </div>
            )}
            {event.description && (
              <div className="timeline-desc">{event.description}</div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}