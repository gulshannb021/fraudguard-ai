import { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { getCase, refreshCase } from "../services/api";
import RiskBadge from "../components/RiskBadge";
import EvidenceCard from "../components/EvidenceCard";
import ActionCard from "../components/ActionCard";
import CaseTimeline from "../components/CaseTimeline";
import "./CaseDetails.css";

export default function CaseDetails() {
  const { caseId } = useParams();
  const [caseData, setCaseData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await getCase(caseId);
      setCaseData(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await refreshCase(caseId);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setRefreshing(false);
    }
  }

  if (loading) return <p>Loading case...</p>;
  if (error) return <p className="error">{error}</p>;
  if (!caseData) return <p>Case not found.</p>;

  const {
    case_id, transaction_id, trigger, status, risk_assessment,
    evidence = [], findings = [], recommended_actions = [],
    timeline = [], explanation,
  } = caseData;

  return (
    <div className="case-details">
      <div className="case-details-header">
        <div>
          <Link to="/cases">&larr; All cases</Link>
          <h1>{case_id}</h1>
        </div>
        <button onClick={handleRefresh} disabled={refreshing}>
          {refreshing ? "Refreshing..." : "Refresh Investigation"}
        </button>
      </div>

      <section className="card">
        <h2>Case Summary</h2>
        <div className="summary-grid">
          <div><span>Trigger</span><strong>{trigger?.type} ({trigger?.source})</strong></div>
          <div><span>Status</span><strong>{status}</strong></div>
          <div><span>Risk</span><RiskBadge level={risk_assessment?.risk_level} confidence={risk_assessment?.confidence} /></div>
          <div><span>Risk Score</span><strong>{risk_assessment?.risk_score ?? "-"}</strong></div>
          <div><span>Transaction</span><strong>{transaction_id}</strong></div>
        </div>
      </section>

      <section className="card">
        <h2>Findings</h2>
        {findings.length === 0 && <p className="muted">No findings yet.</p>}
        {findings.map((f) => (
          <div key={f.finding_id} className="finding-item">
            <div className="finding-title">
              <strong>{f.title}</strong>
              <span className={`finding-status finding-${f.status?.toLowerCase()}`}>{f.status}</span>
            </div>
            <p>{f.description}</p>
            <div className="finding-meta">
              <span>Type: {f.finding_type}</span>
              {f.confidence != null && <span>Confidence: {Math.round(f.confidence * 100)}%</span>}
              <span>Evidence: {(f.supporting_evidence_ids || []).join(", ") || "none"}</span>
            </div>
          </div>
        ))}
        {explanation && Object.keys(explanation).length > 0 && (
          <div className="explanation-box">
            <strong>Remaining uncertainty:</strong>{" "}
            {explanation.uncertainty || explanation.summary || JSON.stringify(explanation)}
          </div>
        )}
      </section>

      <section className="card">
        <h2>Evidence</h2>
        {evidence.length === 0 && <p className="muted">No evidence retrieved yet.</p>}
        {evidence.map((e) => (
          <EvidenceCard key={e.evidence_id} evidence={e} />
        ))}
      </section>

      <section className="card">
        <h2>Recommended Actions</h2>
        {recommended_actions.length === 0 && <p className="muted">No actions recommended.</p>}
        {recommended_actions.map((a) => (
          <ActionCard key={a.action_id} action={a} caseId={case_id} onUpdated={load} />
        ))}
      </section>

      <section className="card">
        <h2>Timeline</h2>
        <CaseTimeline events={timeline} />
      </section>
    </div>
  );
}