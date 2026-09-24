import "./RiskBadge.css";

const RISK_COLORS = {
  LOW: "#2e7d32",
  MEDIUM: "#f9a825",
  HIGH: "#e65100",
  CRITICAL: "#c62828",
  UNKNOWN: "#616161",
};

export default function RiskBadge({ level, confidence }) {
  const safeLevel = level && RISK_COLORS[level] ? level : "UNKNOWN";
  return (
    <span
      className="risk-badge"
      style={{ backgroundColor: RISK_COLORS[safeLevel] }}
      title={
        confidence != null
          ? `${safeLevel} risk, ${Math.round(confidence * 100)}% confidence`
          : safeLevel
      }
    >
      {safeLevel}
      {confidence != null && (
        <span className="risk-badge-confidence">
          {" "}
          {Math.round(confidence * 100)}%
        </span>
      )}
    </span>
  );
}