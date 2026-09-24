from typing import Any, Dict

from app.services.tigergraph import (
    get_transaction_context,
    get_device_neighbors,
)


def investigate(state: Dict[str, Any]) -> Dict[str, Any]:

    transaction_id = str(state["transaction_id"])

    result = {
        **state,
        "investigation_status": "INVESTIGATING",
        "evidence": [],
        "findings": [],
        "risk_assessment": {},
        "uncertainty_reasons": [],
        "evidence_requests": [],
        "recommended_actions": [],
        "approval_requirements": [],
        "explanation": "",
    }

    # -----------------------------------------
    # TIGERGRAPH
    # -----------------------------------------

    graph = get_transaction_context(transaction_id)

    if graph.get("error"):
        result["investigation_status"] = "NEEDS_MORE_EVIDENCE"
        result["uncertainty_reasons"].append(
            "TigerGraph evidence unavailable"
        )
        result["recommended_actions"] = [{
            "action": "ESCALATE_TO_ANALYST",
            "route": "auto",
            "reason": "R8: evidence is unavailable"
        }]
        return result

    result["evidence"].append({
        "source": "graph",
        "ref": "transaction_context",
        "data": graph
    })

    # -----------------------------------------
    # DEVICE / SHARED ORIGIN
    # -----------------------------------------

    try:
        device = get_device_neighbors(transaction_id)

        result["evidence"].append({
            "source": "graph",
            "ref": "device_neighbors",
            "data": device
        })
    except Exception as e:
        result["uncertainty_reasons"].append(
            f"Device evidence unavailable: {str(e)}"
        )

    # -----------------------------------------
    # BASIC RISK
    # -----------------------------------------

    risk_score = state.get("risk_score")

    if risk_score is None:
        risk_score = 0.0

    # IMPORTANT:
    # risk_score is NOT treated as fraud probability.

    result["risk_assessment"] = {
        "risk_score": risk_score,
        "risk_level": (
            "HIGH" if risk_score >= 0.70
            else "MEDIUM" if risk_score >= 0.30
            else "LOW"
        ),
        "confidence": 0.30,
        "reason": (
            "Bank model score used as an investigation trigger; "
            "it is not treated as a fraud verdict."
        )
    }

    # -----------------------------------------
    # DEFAULT UNCERTAINTY
    # -----------------------------------------

    result["uncertainty_reasons"].append(
        "Fraud outcome requires graph and historical evidence"
    )

    # -----------------------------------------
    # POLICY-SAFE INITIAL ACTION
    # -----------------------------------------

    result["recommended_actions"] = [{
        "action": "VERIFY_WITH_CUSTOMER",
        "route": "auto",
        "reason": (
            "R1: a weak or incomplete signal should be verified "
            "before blocking."
        )
    }]

    result["evidence_requests"] = [{
        "type": "customer_validation",
        "asked_after_step": 1,
        "assumed_response": (
            "Customer response must be supplied or simulated "
            "by the investigation workflow."
        )
    }]

    result["investigation_status"] = "NEEDS_MORE_EVIDENCE"

    result["explanation"] = (
        f"Transaction {transaction_id} was investigated using "
        "TigerGraph evidence. The bank risk score was treated "
        "as an investigation trigger rather than a fraud verdict. "
        "Additional evidence is required before a blocking action."
    )

    return result