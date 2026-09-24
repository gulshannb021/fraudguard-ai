from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.investigator import Investigator


router = APIRouter(
    prefix="/api/investigations",
    tags=["Investigations"]
)


class InvestigationRequest(BaseModel):
    transaction_id: str
    trigger_type: str = "FRAUD_SIGNAL"
    source: str = "BANK_RISK_MODEL"


@router.post("")
def create_investigation(request: InvestigationRequest):
    """
    Investigate a transaction from the API.

    The transaction must exist in the supplied HHGOA dataset.
    The API finds the corresponding benchmark case and runs the
    complete fraud investigation engine.
    """

    try:
        transaction_id = int(request.transaction_id)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="transaction_id must be a numeric TransactionID"
        )

    investigator = Investigator()

    try:
        row = investigator.con.execute(
            """
            SELECT case_id
            FROM case_pack
            WHERE flagged_txn_id = ?
            LIMIT 1
            """,
            (transaction_id,)
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No HHGOA benchmark case found for transaction {transaction_id}"
            )

        result = investigator.investigate(row["case_id"])

        # Preserve the API trigger information.
        result["trigger_type"] = request.trigger_type
        result["source"] = request.source

        return result

    finally:
        investigator.close()


@router.get("/{case_id}")
def get_investigation(case_id: str):
    """Run/retrieve a complete HHGOA investigation for a benchmark case."""

    investigator = Investigator()

    try:
        return investigator.investigate(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    finally:
        investigator.close()


@router.post("/run-all")
def run_all_investigations():
    """
    Run all 20 HHGOA benchmark cases and write the required JSON files.
    """

    investigator = Investigator()

    try:
        files = investigator.run_all()

        return {
            "status": "completed",
            "cases_generated": len(files),
            "files": files
        }

    finally:
        investigator.close()