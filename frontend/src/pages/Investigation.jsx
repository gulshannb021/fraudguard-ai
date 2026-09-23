import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createInvestigation } from "../services/api";
import "./Investigation.css";

export default function Investigation() {
  const [transactionId, setTransactionId] = useState("");
  const [triggerType, setTriggerType] = useState("FRAUD_SIGNAL");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await createInvestigation({
        transaction_id: transactionId,
        trigger_type: triggerType,
      });
      navigate(`/cases/${result.case_id}`);
    } catch (e2) {
      setError(e2.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="investigation-page">
      <h1>Start Investigation</h1>
      <form onSubmit={handleSubmit} className="investigation-form">
        <label>
          Transaction ID
          <input
            value={transactionId}
            onChange={(e) => setTransactionId(e.target.value)}
            placeholder="TXN-1001"
            required
          />
        </label>
        <label>
          Trigger Type
          <select value={triggerType} onChange={(e) => setTriggerType(e.target.value)}>
            <option value="FRAUD_SIGNAL">FRAUD_SIGNAL</option>
            <option value="MANUAL_REVIEW">MANUAL_REVIEW</option>
            <option value="RULE_TRIGGER">RULE_TRIGGER</option>
          </select>
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Starting..." : "Start Investigation"}
        </button>
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  );
}