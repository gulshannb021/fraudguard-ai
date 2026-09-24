from pathlib import Path
import json

from fastapi import APIRouter, HTTPException, Query

from app.config import CASES_DIR
from app.investigator import Investigator

router = APIRouter(prefix="/api/cases", tags=["Cases"])


def _risk_level(probability):
    p = float(probability or 0)

    if p >= 0.85:
        return "HIGH"

    if p >= 0.70:
        return "MEDIUM"

    return "LOW"


def _load_case(case_id):
    path = Path(CASES_DIR) / f"{case_id}.json"

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Case {case_id} not found",
        )

    return json.loads(path.read_text())


def _normalize_case(data):
    case = data.get("case", {})
    probability = float(
        case.get("fraud_probability", 0) or 0
    )

    # ---------------------------------------------------------
    # EVIDENCE
    # ---------------------------------------------------------

    evidence = case.get("evidence", []) or []

    normalized_evidence = []
    findings = []

    for i, item in enumerate(evidence, 1):
        evidence_id = (
            f"{case.get('case_id', data.get('case_id', 'CASE'))}-E{i}"
        )

        normalized_evidence.append({
            "evidence_id": evidence_id,
            "type": item.get("source", "investigation"),
            "title": item.get(
                "claim",
                "Investigation evidence",
            ),
            "description": item.get("claim", ""),
            "source": item.get(
                "source",
                "investigation_engine",
            ),
            "reference": item.get("ref"),
            "entity_ids": item.get("entity_ids", []),
            "relevance": item.get("relevance", "UNKNOWN"),
            "confidence": item.get(
                "confidence",
                probability,
            ),
        })

        findings.append({
            "finding_id": evidence_id,
            "title": item.get(
                "claim",
                "Evidence",
            ),
            "description": item.get("claim", ""),
            "finding_type": item.get(
                "source",
                "investigation",
            ),
            "status": "SUPPORTED",
            "confidence": probability,
            "supporting_evidence_ids": [
                evidence_id
            ],
        })

    # ---------------------------------------------------------
    # NEXT BEST ACTIONS
    # ---------------------------------------------------------

    nba = data.get("next_best_actions", {}) or {}
    final_actions = nba.get("final", []) or []

    recommended_actions = []

    for i, action in enumerate(final_actions, 1):
        action_id = (
            f"{case.get('case_id', data.get('case_id', 'CASE'))}"
            f"-A{i}"
        )

        recommended_actions.append({
            "action_id": action_id,
            "action_type": action.get(
                "action",
                "ESCALATE_TO_ANALYST",
            ),
            "route": action.get(
                "route",
                "auto",
            ),
            "reason": action.get(
                "reason",
                "",
            ),

            # IMPORTANT:
            # Preserve approval/execution state from the
            # case JSON instead of resetting everything to PENDING.
            "approval_status": action.get(
                "approval_status",
                "PENDING",
            ),
            "execution_status": action.get(
                "execution_status",
                "PENDING",
            ),
            "status": action.get(
                "approval_status",
                "PENDING",
            ),

            "rejection_reason": action.get(
                "rejection_reason"
            ),

            "rule": action.get("rule"),
        })

    # ---------------------------------------------------------
    # TIMELINE
    # ---------------------------------------------------------

    timeline = []

    for i, tool in enumerate(
        data.get("tool_calls", []) or [],
        1,
    ):
        if isinstance(tool, dict):
            timeline.append({
                "event_id": f"T{i}",
                "type": "TOOL_CALL",
                "title": tool.get(
                    "tool",
                    "Investigation step",
                ),
                "description": tool.get(
                    "result",
                    tool.get("name", ""),
                ),
            })
        else:
            timeline.append({
                "event_id": f"T{i}",
                "type": "TOOL_CALL",
                "title": str(tool),
                "description": "",
            })

    # ---------------------------------------------------------
    # TRANSACTION
    # ---------------------------------------------------------

    affected = case.get(
        "affected_txn_ids",
        [],
    ) or []

    transaction_id = (
        affected[0]
        if affected
        else case.get(
            "first_suspicious_txn_id"
        )
    )

    # ---------------------------------------------------------
    # FINAL RESPONSE
    # ---------------------------------------------------------

    return {
        "case_id": case.get(
            "case_id",
            data.get("case_id"),
        ),

        "transaction_id": transaction_id,

        "trigger": {
            "type": data.get(
                "trigger_type",
                "FRAUD_SIGNAL",
            ),
            "source": data.get(
                "source",
                "BANK_RISK_MODEL",
            ),
        },

        "status": case.get(
            "status",
            "open",
        ),

        "risk_assessment": {
            "risk_score": probability,
            "confidence": probability,
            "risk_level": _risk_level(
                probability
            ),
            "verdict": case.get(
                "verdict"
            ),
            "pattern": case.get(
                "pattern"
            ),
        },

        "evidence": normalized_evidence,

        "findings": findings,

        "recommended_actions": recommended_actions,

        "timeline": timeline,

        "explanation": {
            "summary": case.get(
                "summary",
                "",
            ),
            "uncertainty": data.get(
                "stop_reason",
                "",
            ),
            "pattern_description": case.get(
                "pattern_description",
                "",
            ),
        },

        "raw_case": data,
    }


# -------------------------------------------------------------
# LIST CASES
# -------------------------------------------------------------

@router.get("")
def list_cases(
    status: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
):
    results = []

    for path in sorted(
        Path(CASES_DIR).glob("*.json")
    ):
        try:
            item = _normalize_case(
                json.loads(
                    path.read_text()
                )
            )

            if (
                status
                and item["status"] != status
            ):
                continue

            if (
                risk_level
                and item["risk_assessment"][
                    "risk_level"
                ] != risk_level
            ):
                continue

            results.append(item)

        except Exception:
            continue

    return {
        "cases": results[:limit],
        "total": len(results),
    }


# -------------------------------------------------------------
# GET SINGLE CASE
# -------------------------------------------------------------

@router.get("/{case_id}")
def get_case(case_id: str):
    return _normalize_case(
        _load_case(case_id)
    )


# -------------------------------------------------------------
# REFRESH CASE
# -------------------------------------------------------------

@router.post("/{case_id}/refresh")
def refresh_case(case_id: str):
    investigator = Investigator()

    try:
        result = investigator.investigate(
            case_id
        )

        return _normalize_case(result)

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    finally:
        investigator.close()