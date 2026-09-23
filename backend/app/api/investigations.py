from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from app.agent.workflow import investigate


router = APIRouter(
    prefix="/api/investigations",
    tags=["Investigations"]
)


class InvestigationRequest(BaseModel):
    transaction_id: str
    trigger_type: str
    source: str


class InvestigationResponse(BaseModel):
    case_id: str
    transaction_id: str
    status: str
    findings: list
    recommended_actions: list


@router.post("", response_model=InvestigationResponse)
def create_investigation(request: InvestigationRequest):

    case_id = f"CASE-{uuid4().hex[:8].upper()}"

    result = investigate({
        "case_id": case_id,
        "transaction_id": request.transaction_id,
        "trigger": request.trigger_type
    })

    return {
        "case_id": case_id,
        "transaction_id": request.transaction_id,
        "status": result["investigation_status"],
        "findings": result["findings"],
        "recommended_actions": result["recommended_actions"]
    }