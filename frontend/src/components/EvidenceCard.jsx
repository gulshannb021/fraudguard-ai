import "./EvidenceCard.css";

export default function EvidenceCard({ evidence }) {
  const {
    evidence_id,
    type,
    source,
    title,
    description,
    entity_ids = [],
    relevance,
    confidence,
    timestamp,
  } = evidence;

  const visibleEntities = entity_ids.slice(0, 5);
  const remainingCount = Math.max(entity_ids.length - 5, 0);

  return (
    <div className="evidence-card" data-relevance={relevance || "LOW"}>
      <div className="evidence-card-header">
        <span className="evidence-type">{type}</span>
        <span className="evidence-source">{source}</span>
      </div>

      <h4>{title}</h4>

      <p>{description}</p>

      {entity_ids.length > 0 && (
        <div className="evidence-entities">
          {visibleEntities.map((id) => (
            <span key={id} className="entity-chip">
              {id}
            </span>
          ))}

          {remainingCount > 0 && (
            <span className="entity-chip entity-more">
              +{remainingCount} more
            </span>
          )}
        </div>
      )}

      <div className="evidence-card-footer">
        <span>Relevance: {relevance || "UNKNOWN"}</span>

        {confidence != null && (
          <span>Confidence: {Math.round(confidence * 100)}%</span>
        )}

        {timestamp && (
          <span>{new Date(timestamp).toLocaleString()}</span>
        )}

        <span className="evidence-id">{evidence_id}</span>
      </div>
    </div>
  );
}