from typing import Any, Dict, List, Optional


def _action(
    action: str,
    route: str,
    reason: str,
) -> Dict[str, str]:
    return {
        "action": action,
        "route": route,
        "reason": reason,
    }


def _dedupe(actions: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Remove duplicate action + route combinations while preserving order.
    """
    seen = set()
    result = []

    for item in actions:
        key = (
            item.get("action"),
            item.get("route"),
        )

        if key not in seen:
            seen.add(key)
            result.append(item)

    return result


def decide_policy(
    fraud_probability: float,
    pattern: str,
    exposure_usd: float,
    evidence_count: int,
    shared_origin: bool = False,
    customer_response: Optional[str] = None,
) -> Dict[str, Any]:
    """
    FraudGuard policy decision engine.

    Produces:
        initial     -> recommendation before additional evidence
        final       -> recommendation after evidence/verification
        what_changed -> explanation of policy changes

    Policy:
        R1  Weak single signal
        R2  Customer denies
        R3  Customer confirms
        R4  No reply
        R5  Card testing
        R6  Shared origin
        R7  Disputed legitimate recurring activity
        R8  Uncertain/high-confidence investigation
        R9  Undocumented coordinated/repeated abuse
        R10 BLOCK_ALL_CARDS safety restriction
    """

    p = max(0.0, min(1.0, float(fraud_probability)))
    exposure = max(0.0, float(exposure_usd or 0.0))
    evidence_count = max(0, int(evidence_count or 0))
    pattern = pattern or "undocumented"

    initial: List[Dict[str, str]] = []
    final: List[Dict[str, str]] = []

    # =========================================================
    # INITIAL NEXT-BEST ACTION
    #
    # This represents the action selected before additional
    # evidence is gathered.
    # =========================================================

    if customer_response is None:

        # R5 has a deterministic initial response.
        if pattern == "card_testing":
            initial.extend(
                [
                    _action(
                        "DECLINE_TRANSACTION",
                        "l1_team_lead",
                        (
                            "R5: card-testing activity requires the "
                            "suspicious transaction to be declined."
                        ),
                    ),
                    _action(
                        "STEP_UP_AUTH",
                        "auto",
                        (
                            "R5: card-testing activity requires "
                            "additional authentication."
                        ),
                    ),
                ]
            )

        # Shared-origin activity immediately requires monitoring
        # connected cards and creating a case.
        elif shared_origin:
            initial.extend(
                [
                    _action(
                        "CREATE_CASE",
                        "auto",
                        (
                            "R6: shared-origin activity requires an "
                            "investigation case."
                        ),
                    ),
                    _action(
                        "MONITOR_CONNECTED_CARDS",
                        "auto",
                        (
                            "R6: monitor cards connected through the "
                            "shared origin."
                        ),
                    ),
                ]
            )

        # Low-confidence activity.
        elif p < 0.30:
            initial.append(
                _action(
                    "MONITOR_CARD",
                    "auto",
                    (
                        "Initial assessment is low risk; monitor the "
                        "affected card while investigation continues."
                    ),
                )
            )

        # R1 / medium uncertainty.
        elif p < 0.70:
            initial.extend(
                [
                    _action(
                        "VERIFY_WITH_CUSTOMER",
                        "auto",
                        (
                            "R1: fraud probability is below 0.70; "
                            "customer verification is required before "
                            "stronger action."
                        ),
                    ),
                    _action(
                        "CREATE_CASE",
                        "auto",
                        (
                            "R1: evidence verification has been requested, "
                            "so an investigation case must be created."
                        ),
                    ),
                ]
            )

        # Elevated risk.
        elif p < 0.85:
            initial.extend(
                [
                    _action(
                        "CREATE_CASE",
                        "auto",
                        (
                            "Fraud probability is at least 0.70; create "
                            "an investigation case while gathering "
                            "additional evidence."
                        ),
                    ),
                    _action(
                        "MONITOR_CARD",
                        "auto",
                        (
                            "Elevated fraud probability requires "
                            "continued monitoring of the affected card."
                        ),
                    ),
                ]
            )

        # High-confidence case.
        else:
            initial.extend(
                [
                    _action(
                        "CREATE_CASE",
                        "auto",
                        (
                            "R8: high-confidence fraud requires a "
                            "formal investigation case."
                        ),
                    ),
                    _action(
                        "ESCALATE_TO_ANALYST",
                        "auto",
                        (
                            "R8: high-confidence fraud requires "
                            "fraud analyst review."
                        ),
                    ),
                ]
            )

    # =========================================================
    # R3 — CUSTOMER CONFIRMS ACTIVITY
    # =========================================================

    if customer_response == "confirmed":

        final.append(
            _action(
                "CLOSE_NO_FRAUD",
                "auto",
                (
                    "R3: customer confirmed the activity is legitimate; "
                    "close the investigation without fraud action."
                ),
            )
        )

        return {
            "initial": _dedupe(initial),
            "final": _dedupe(final),
            "what_changed": [
                "R3 verification response resolved the investigation as legitimate."
            ],
        }

    # =========================================================
    # R2 — CUSTOMER DENIES ACTIVITY
    # =========================================================

    if customer_response == "denied":

        block_route = (
            "l1_team_lead"
            if exposure <= 2500
            else "l2_fraud_manager"
        )

        final.append(
            _action(
                "BLOCK_CARD",
                block_route,
                (
                    "R2: customer denied the activity; block the "
                    "affected card according to the exposure-based "
                    "approval route."
                ),
            )
        )

        final.append(
            _action(
                "CREATE_CASE",
                "auto",
                (
                    "R2: customer denial requires creation of a "
                    "fraud investigation case."
                ),
            )
        )

        if exposure > 1000 or shared_origin:
            final.append(
                _action(
                    "FILE_REPORT",
                    "l2_fraud_manager",
                    (
                        "R2: customer denial plus qualifying exposure "
                        "or shared-origin evidence meets the reporting "
                        "condition."
                    ),
                )
            )

        return {
            "initial": _dedupe(initial),
            "final": _dedupe(final),
            "what_changed": [
                (
                    "Customer denial changed the investigation to "
                    "confirmed suspicious activity requiring card blocking."
                )
            ],
        }

    # =========================================================
    # R5 — CARD TESTING
    # =========================================================

    if pattern == "card_testing":

        final.extend(
            [
                _action(
                    "DECLINE_TRANSACTION",
                    "l1_team_lead",
                    (
                        "R5: card-testing activity requires the "
                        "suspicious transaction to be declined."
                    ),
                ),
                _action(
                    "STEP_UP_AUTH",
                    "auto",
                    (
                        "R5: card-testing activity requires "
                        "additional authentication."
                    ),
                ),
            ]
        )

        if exposure > 100:

            block_route = (
                "l1_team_lead"
                if exposure <= 2500
                else "l2_fraud_manager"
            )

            final.append(
                _action(
                    "BLOCK_CARD",
                    block_route,
                    (
                        "R5: card-testing activity includes a cleared "
                        "purchase above $100; block the affected card."
                    ),
                )
            )

    # =========================================================
    # R6 — SHARED ORIGIN
    # =========================================================

    if shared_origin:

        final.extend(
            [
                _action(
                    "CREATE_CASE",
                    "auto",
                    (
                        "R6: shared-origin activity requires an "
                        "investigation case."
                    ),
                ),
                _action(
                    "FILE_REPORT",
                    "l2_fraud_manager",
                    (
                        "R6: shared device, region, or related origin "
                        "requires reporting."
                    ),
                ),
                _action(
                    "MONITOR_CONNECTED_CARDS",
                    "auto",
                    (
                        "R6: monitor cards connected through the "
                        "shared origin."
                    ),
                ),
            ]
        )

    # =========================================================
    # R9 — UNDOCUMENTED COORDINATED / REPEATED ABUSE
    # =========================================================

    if pattern == "undocumented" and p >= 0.70:

        final.extend(
            [
                _action(
                    "CREATE_CASE",
                    "auto",
                    (
                        "R9: undocumented suspicious activity requires "
                        "creation of an investigation case."
                    ),
                ),
                _action(
                    "FILE_REPORT",
                    "l2_fraud_manager",
                    (
                        "R9: undocumented coordinated or repeated abuse "
                        "requires a report."
                    ),
                ),
                _action(
                    "ESCALATE_TO_ANALYST",
                    "auto",
                    (
                        "R9: undocumented suspicious activity requires "
                        "fraud analyst review."
                    ),
                ),
            ]
        )

    # =========================================================
    # R8 — UNCERTAIN / CONFLICTING EVIDENCE
    # =========================================================

    if (
        0.15 < p < 0.85
        and (
            exposure > 500
            or evidence_count < 2
        )
    ):

        final.append(
            _action(
                "ESCALATE_TO_ANALYST",
                "auto",
                (
                    "R8: fraud probability remains uncertain or evidence "
                    "is conflicting, with material exposure or insufficient "
                    "independent evidence."
                ),
            )
        )

    # =========================================================
    # R1 — WEAK SINGLE SIGNAL
    # =========================================================

    if p < 0.70 and evidence_count <= 1:

        final.extend(
            [
                _action(
                    "VERIFY_WITH_CUSTOMER",
                    "auto",
                    (
                        "R1: a weak single signal with fraud probability "
                        "below 0.70 requires customer verification "
                        "before blocking."
                    ),
                ),
                _action(
                    "CREATE_CASE",
                    "auto",
                    (
                        "R1: evidence verification has been requested, "
                        "so an investigation case must be created."
                    ),
                ),
            ]
        )

    # =========================================================
    # R4 — NO CUSTOMER RESPONSE
    # =========================================================

    if customer_response == "no_reply":

        final.extend(
            [
                _action(
                    "MONITOR_CARD",
                    "auto",
                    (
                        "R4: no customer response after 24 hours "
                        "requires continued card monitoring."
                    ),
                ),
                _action(
                    "DECLINE_TRANSACTION",
                    "l1_team_lead",
                    (
                        "R4: pending authorizations should be declined "
                        "while verification remains unresolved."
                    ),
                ),
            ]
        )

        if exposure > 500:
            final.append(
                _action(
                    "ESCALATE_TO_ANALYST",
                    "auto",
                    (
                        "R4: unresolved exposure exceeds $500, "
                        "requiring analyst escalation."
                    ),
                )
            )

    # =========================================================
    # R7 — DISPUTED BUT APPARENTLY LEGITIMATE RECURRING ACTIVITY
    # =========================================================

    if (
        customer_response == "disputed"
        and p < 0.50
    ):

        final.extend(
            [
                _action(
                    "CREATE_CASE",
                    "auto",
                    (
                        "R7: disputed recurring activity requires "
                        "an investigation case."
                    ),
                ),
                _action(
                    "VERIFY_WITH_CUSTOMER",
                    "auto",
                    (
                        "R7: disputed recurring activity requires "
                        "customer verification."
                    ),
                ),
                _action(
                    "WARN_CUSTOMER",
                    "auto",
                    (
                        "R7: warn the customer about disputed recurring "
                        "activity without blocking the card."
                    ),
                ),
            ]
        )

    # =========================================================
    # HIGH-CONFIDENCE FRAUD
    # =========================================================

    if p >= 0.85:

        final.extend(
            [
                _action(
                    "CREATE_CASE",
                    "auto",
                    (
                        "R8: fraud probability reached the high-confidence "
                        "threshold and requires a formal case."
                    ),
                ),
                _action(
                    "ESCALATE_TO_ANALYST",
                    "auto",
                    (
                        "R8: high-confidence fraud requires fraud "
                        "analyst review."
                    ),
                ),
            ]
        )

    # =========================================================
    # LOW-CONFIDENCE LEGITIMATE ACTIVITY
    # =========================================================

    if (
        p <= 0.15
        and evidence_count >= 2
    ):

        final.append(
            _action(
                "CLOSE_NO_FRAUD",
                "auto",
                (
                    "R3: fraud probability is at or below 0.15 and "
                    "at least two independent evidence pieces support "
                    "closing the case."
                ),
            )
        )

    # =========================================================
    # CREATE_CASE THRESHOLD
    # =========================================================

    if 0.30 <= p < 0.85:

        final.append(
            _action(
                "CREATE_CASE",
                "auto",
                (
                    "CREATE_CASE policy threshold: fraud probability "
                    "is at least 0.30."
                ),
            )
        )

    # =========================================================
    # MEDIUM-CONFIDENCE INVESTIGATION
    # =========================================================

    if (
        0.15 < p < 0.70
        and pattern != "card_testing"
        and customer_response is None
    ):

        final.append(
            _action(
                "STEP_UP_AUTH",
                "auto",
                (
                    "R1: fraud probability is below 0.70, so step-up "
                    "authentication is preferred before blocking."
                ),
            )
        )

    # =========================================================
    # REPORTING CONDITION
    # =========================================================

    if (
        p >= 0.70
        and (
            exposure > 1000
            or shared_origin
            or pattern == "undocumented"
        )
    ):

        final.append(
            _action(
                "FILE_REPORT",
                "l2_fraud_manager",
                (
                    "Reporting policy: strongly suspected or confirmed "
                    "fraud meets the exposure, shared-origin, or "
                    "undocumented-activity reporting condition."
                ),
            )
        )

    # =========================================================
    # R10 SAFETY RULE
    #
    # BLOCK_ALL_CARDS is never automatically recommended.
    # =========================================================

    final = [
        item
        for item in final
        if item.get("action") != "BLOCK_ALL_CARDS"
    ]

    # =========================================================
    # DEDUPLICATE
    # =========================================================

    initial = _dedupe(initial)
    final = _dedupe(final)

    # =========================================================
    # WHAT CHANGED
    # =========================================================

    initial_keys = {
        (item["action"], item["route"])
        for item in initial
    }

    final_keys = {
        (item["action"], item["route"])
        for item in final
    }

    what_changed: List[str] = []

    for item in final:
        key = (item["action"], item["route"])

        if key not in initial_keys:
            what_changed.append(
                f"Added {item['action']} via {item['route']}."
            )

    for item in initial:
        key = (item["action"], item["route"])

        if key not in final_keys:
            what_changed.append(
                f"Removed {item['action']} via {item['route']}."
            )

    return {
        "initial": initial,
        "final": final,
        "what_changed": what_changed,
    }