import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getCases } from "../services/api";
import { CaseStatus, RiskLevel } from "../types/caseTypes";
import RiskBadge from "../components/RiskBadge";
import "./CaseList.css";

export default function CaseList() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [riskFilter, setRiskFilter] = useState("");

  useEffect(() => {
    loadCases();
  }, [statusFilter, riskFilter]);

  async function loadCases() {
    setLoading(true);
    setError(null);
    try {
      const filters = {};
      if (statusFilter) filters.status = statusFilter;
      if (riskFilter) filters.risk_level = riskFilter;
      const data = await getCases(filters);
      setCases(data.cases || data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="case-list-page">
      <h1>Cases</h1>

      <div className="filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          {Object.values(CaseStatus).map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)}>
          <option value="">All risk levels</option>
          {Object.values(RiskLevel).map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
      </div>

      {loading && <p>Loading cases...</p>}
      {error && <p className="error">{error}</p>}

      {!loading && !error && (
        <table className="case-table">
          <thead>
            <tr>
              <th>Case ID</th>
              <th>Transaction</th>
              <th>Risk</th>
              <th>Status</th>
              <th>Trigger</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((c) => (
              <tr key={c.case_id}>
                <td><Link to={`/cases/${c.case_id}`}>{c.case_id}</Link></td>
                <td>{c.transaction_id}</td>
                <td><RiskBadge level={c.risk_assessment?.risk_level} /></td>
                <td>{c.status}</td>
                <td>{c.trigger?.type || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}