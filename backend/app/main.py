from pathlib import Path
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.investigations import router as investigation_router
from app.api.cases import router as cases_router
from app.api.actions import router as actions_router
from app.config import CASES_DIR


app = FastAPI(
    title="FraudGuard AI",
    description="Agentic Fraud Investigation and Next-Best Action System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(investigation_router)
app.include_router(cases_router)
app.include_router(actions_router)


@app.get("/")
def root():
    return {"name": "FraudGuard AI", "status": "running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/api/dashboard/summary")
def dashboard_summary():
    cases = []

    for path in Path(CASES_DIR).glob("*.json"):
        try:
            cases.append(json.loads(path.read_text()).get("case", {}))
        except Exception:
            continue

    return {
        "total_cases": len(cases),
        "open_cases": sum(
            1 for c in cases
            if c.get("status") in ("open", "escalated")
        ),
        "high_risk_investigations": sum(
            1 for c in cases
            if float(c.get("fraud_probability", 0) or 0) >= 0.85
        ),
        "cases_awaiting_approval": 0,
        "investigations_needing_evidence": sum(
            1 for c in cases
            if c.get("verdict") == "uncertain"
        ),
    }
