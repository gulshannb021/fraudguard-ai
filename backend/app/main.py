from fastapi import FastAPI

from app.api.investigations import router as investigation_router


app = FastAPI(
    title="FraudGuard AI",
    description="Agentic Fraud Investigation and Next-Best Action System",
    version="1.0.0"
)


app.include_router(investigation_router)


@app.get("/")
def root():
    return {
        "name": "FraudGuard AI",
        "status": "running"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }