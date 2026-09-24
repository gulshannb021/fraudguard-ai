import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import CASES_DIR

router = APIRouter(prefix="/api/actions", tags=["Actions"])


class RejectRequest(BaseModel):
    reason: str = "Rejected by analyst"


def _load_case(case_id: str):
    case_path = CASES_DIR / f"{case_id}.json"

    if not case_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Case {case_id} not found",
        )

    with open(case_path, "r", encoding="utf-8") as f:
        return json.load(f), case_path


def _save_case(case_path: Path, data: dict):
    with open(case_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _find_action(case_id: str, action_id: str):
    data, case_path = _load_case(case_id)

    actions = data.get("next_best_actions", {})
    final_actions = actions.get("final", [])

    for index, action in enumerate(final_actions):
        generated_id = f"{case_id}-A{index + 1}"

        if generated_id == action_id:
            return data, case_path, action, index

    raise HTTPException(
        status_code=404,
        detail=f"Action {action_id} not found in case {case_id}",
    )


@router.post("/{action_id}/approve")
def approve_action(action_id: str):
    parts = action_id.rsplit("-A", 1)

    if len(parts) != 2:
        raise HTTPException(
            status_code=400,
            detail="Invalid action ID",
        )

    case_id = parts[0]

    data, case_path, action, index = _find_action(
        case_id,
        action_id,
    )

    action["approval_status"] = "APPROVED"
    action["execution_status"] = "APPROVED"

    # Keep the initial action state synchronized too.
    initial_actions = data.get("next_best_actions", {}).get("initial", [])

    if index < len(initial_actions):
        initial_actions[index]["approval_status"] = "APPROVED"
        initial_actions[index]["execution_status"] = "APPROVED"

    _save_case(case_path, data)

    return {
        "status": "approved",
        "action_id": action_id,
        "case_id": case_id,
        "action": action,
    }


@router.post("/{action_id}/reject")
def reject_action(action_id: str, request: RejectRequest):
    parts = action_id.rsplit("-A", 1)

    if len(parts) != 2:
        raise HTTPException(
            status_code=400,
            detail="Invalid action ID",
        )

    case_id = parts[0]

    data, case_path, action, index = _find_action(
        case_id,
        action_id,
    )

    action["approval_status"] = "REJECTED"
    action["execution_status"] = "REJECTED"
    action["rejection_reason"] = request.reason

    initial_actions = data.get("next_best_actions", {}).get("initial", [])

    if index < len(initial_actions):
        initial_actions[index]["approval_status"] = "REJECTED"
        initial_actions[index]["execution_status"] = "REJECTED"
        initial_actions[index]["rejection_reason"] = request.reason

    _save_case(case_path, data)

    return {
        "status": "rejected",
        "action_id": action_id,
        "case_id": case_id,
        "reason": request.reason,
        "action": action,
    }