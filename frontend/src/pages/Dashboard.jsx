import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getCases, getDashboardSummary } from "../services/api";
import RiskBadge from "../components/RiskBadge";
import "./Dashboard.css";

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadDashboard();
  }, []);

  async function loadDashboard() {
    setLoading(true);
    setError(null);
    try {
      const [summaryData, casesData] = await Promise.all([
        getDashboardSummary(),
        getCases({ sort: "updated_at_desc", limit: 10 }),
      ]);
      setSummary(summaryData);
      setCases(casesData.cases || casesData);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <p className="dashboard-status">Loading dashboard...</p>;
  if (error) return <p className="dashboard-status error">{error}</p>;

  return (
    <div className="dashboard">
      <h1>FRAUDGUARD AI</h1>

      <div className="stat-grid">
        <StatCard label="Open Cases" value={summary?.open_cases} />
        <StatCard label="High Risk" value={summary?.high_risk_investigations} />
        <StatCard label="Pending Review" value={summary?.cases_awaiting_approval} />
        <StatCard label="Total Cases" value={summary?.total_cases} />
        <StatCard label="Needs Evidence" value={summary?.investigations_needing_evidence} />
      </div>

      <h2>Recently Updated Cases</h2>
      <table className="case-table">
        <thead>
          <tr>
            <th>Case ID</th>
            <th>Risk</th>
            <th>Status</th>
            <th>Next Action</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((c) => (
            <tr key={c.case_id}>
              <td>
                <Link to={`/cases/${c.case_id}`}>{c.case_id}</Link>
              </td>
              <td>
                <RiskBadge level={c.risk_assessment?.risk_level} />
              </td>
              <td>{c.status}</td>
              <td>{c.recommended_actions?.[0]?.action_type || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatCard({ label, value }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value ?? "-"}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}