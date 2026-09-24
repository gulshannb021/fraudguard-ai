import { useState } from "react";
import { approveAction, rejectAction } from "../services/api";
import "./ActionCard.css";

export default function ActionCard({ action, caseId, onUpdated }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const {
    action_id,
    action_type,
    reason,
    approval_status,
    execution_status,
    requested_at,
  } = action;

  const needsDecision = approval_status === "PENDING_APPROVAL";

  async function handleApprove() {
    setBusy(true);
    setError(null);
    try {
      await approveAction(action_id);
      onUpdated?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleReject() {
    setBusy(true);
    setError(null);
    try {
      await rejectAction(action_id, "Rejected by analyst");
      onUpdated?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="action-card">
      <div className="action-card-title">
        <strong>{action_type}</strong>
        <span className={`status-pill status-${execution_status?.toLowerCase()}`}>
          {execution_status}
        </span>
      </div>
      <p className="action-reason">{reason}</p>
      <div className="action-meta">
        <span>Case: {caseId}</span>
        <span>Approval: {approval_status}</span>
        {requested_at && (
          <span>{new Date(requested_at).toLocaleString()}</span>
        )}
      </div>

      {needsDecision && (
        <div className="action-buttons">
          <button disabled={busy} className="btn-approve" onClick={handleApprove}>
            APPROVE
          </button>
          <button disabled={busy} className="btn-reject" onClick={handleReject}>
            REJECT
          </button>
        </div>
      )}
      {error && <p className="action-error">{error}</p>}
    </div>
  );
}