from app.agent.state import InvestigationState


def investigate(state: InvestigationState):

    print("Investigating transaction:", state["transaction_id"])

    return {
        **state,
        "investigation_status": "INVESTIGATING",
        "findings": [
            "Investigation started"
        ],
        "recommended_actions": [
            {
                "action": "COLLECT_MORE_EVIDENCE",
                "reason": "Additional evidence is required"
            }
        ]
    }