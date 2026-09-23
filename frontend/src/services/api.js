const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    let errorBody = null;
    try {
      errorBody = await response.json();
    } catch {
      // response wasn't JSON
    }
    const message =
      errorBody?.error?.message || `Request failed: ${response.status}`;
    const err = new Error(message);
    err.code = errorBody?.error?.code || "UNKNOWN_ERROR";
    err.status = response.status;
    throw err;
  }

  if (response.status === 204) return null;
  return response.json();
}

// ---- Cases ----
export function getCases(filters = {}) {
  const params = new URLSearchParams(filters).toString();
  return request(`/api/cases${params ? `?${params}` : ""}`);
}

export function getCase(caseId) {
  return request(`/api/cases/${caseId}`);
}

export function refreshCase(caseId) {
  return request(`/api/cases/${caseId}/refresh`, { method: "POST" });
}

// ---- Investigations ----
export function createInvestigation({ transaction_id, trigger_type }) {
  return request(`/api/investigations`, {
    method: "POST",
    body: JSON.stringify({ transaction_id, trigger_type }),
  });
}

// ---- Actions ----
export function approveAction(actionId) {
  return request(`/api/actions/${actionId}/approve`, { method: "POST" });
}

export function rejectAction(actionId, reason) {
  return request(`/api/actions/${actionId}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

// ---- Dashboard summary ----
export function getDashboardSummary() {
  return request(`/api/dashboard/summary`);
}