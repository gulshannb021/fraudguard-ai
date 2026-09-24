from datetime import datetime, timedelta
from collections import Counter


DOCUMENTED_PATTERNS = {
    "card_testing",
    "card_not_present_fraud",
    "card_not_present_new_device",
    "out_of_region_use",
    "account_takeover",
}


def parse_ts(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def money(value):
    try:
        return round(abs(float(value or 0)), 2)
    except (TypeError, ValueError):
        return 0.0


def independent_evidence_count(evidence):
    """
    Count independent evidence sources.

    Different claims from the same source are not treated as
    independent evidence.
    """
    return len({
        item.get("source")
        for item in evidence
        if item.get("source")
    })


def _evidence(claim, source, ref, entity_ids):
    return {
        "claim": claim,
        "source": source,
        "ref": ref,
        "entity_ids": [str(x) for x in entity_ids if x is not None],
    }


def _same_window(txns, start, end):
    result = []

    for txn in txns:
        ts = parse_ts(txn.get("ts"))

        if ts and start <= ts <= end:
            result.append(txn)

    return result


def detect_card_testing(flagged, card_txns, evidence):
    """
    R5:
    3+ tiny online authorizations, normally under $5,
    within approximately one hour, followed by a larger purchase.
    """

    flagged_ts = parse_ts(flagged.get("ts"))

    if not flagged_ts:
        return False

    candidates = [
        txn
        for txn in card_txns
        if txn.get("channel") == "online"
        and money(txn.get("amount")) < 5
        and parse_ts(txn.get("ts"))
        and parse_ts(txn.get("ts")) <= flagged_ts
    ]

    candidates.sort(key=lambda x: parse_ts(x["ts"]))

    for i in range(len(candidates)):
        window = [
            txn
            for txn in candidates[i:]
            if parse_ts(txn["ts"]) - parse_ts(candidates[i]["ts"])
            <= timedelta(hours=1)
        ]

        if len(window) >= 3:
            small_txns = window[:3]

            evidence.append(
                _evidence(
                    claim=(
                        f"At least three online authorizations under $5 "
                        f"occurred within approximately one hour before "
                        f"transaction {flagged['id']}."
                    ),
                    source="transactions.csv",
                    ref=f"card:{flagged['card_id']}:card_testing",
                    entity_ids=[
                        flagged["card_id"],
                        *[txn["id"] for txn in small_txns],
                    ],
                )
            )

            return True

    return False


def detect_cnp(flagged, card_txns, evidence):
    """
    R1-R4 documented CNP pattern:
    online transactions with unusual/burst activity.
    """

    flagged_ts = parse_ts(flagged.get("ts"))

    if not flagged_ts:
        return False

    start = flagged_ts - timedelta(hours=48)
    end = flagged_ts + timedelta(hours=48)

    online = [
        txn
        for txn in _same_window(card_txns, start, end)
        if txn.get("channel") == "online"
    ]

    if len(online) < 2:
        return False

    evidence.append(
        _evidence(
            claim=(
                f"{len(online)} online transactions occurred within "
                "the 48-hour investigation window."
            ),
            source="transactions.csv",
            ref=f"card:{flagged['card_id']}:cnp_burst",
            entity_ids=[
                flagged["card_id"],
                *[txn["id"] for txn in online[:20]],
            ],
        )
    )

    return True


def detect_new_device(flagged, identity, evidence):
    """
    Documented stronger CNP signal:
    online activity + identity id_15 == New.
    """

    if flagged.get("channel") != "online":
        return False

    if not identity:
        return False

    value = str(identity.get("id_15", "")).strip().lower()

    if value != "new":
        return False

    evidence.append(
        _evidence(
            claim=(
                "The flagged online transaction is associated with an "
                "identity record where id_15 is marked New."
            ),
            source="identity.csv",
            ref=f"identity:{flagged['id']}:id_15",
            entity_ids=[flagged["id"]],
        )
    )

    return True


def detect_out_of_region(flagged, customer_txns, evidence):
    """
    R2/R3 documented out-of-region pattern:

    Card-present purchases in a billing region with no prior history,
    while home-region activity continues.
    """

    if flagged.get("channel") != "in_person":
        return False

    addr1 = flagged.get("addr1")
    addr2 = flagged.get("addr2")

    if addr1 in (None, "") and addr2 in (None, ""):
        return False

    before = [
        txn
        for txn in customer_txns
        if parse_ts(txn.get("ts"))
        and parse_ts(flagged.get("ts"))
        and parse_ts(txn["ts"]) < parse_ts(flagged["ts"])
    ]

    if not before:
        return False

    historical_regions = {
        (txn.get("addr1"), txn.get("addr2"))
        for txn in before
        if txn.get("channel") == "in_person"
    }

    flagged_region = (addr1, addr2)

    if flagged_region in historical_regions:
        return False

    home_activity = [
        txn
        for txn in before
        if txn.get("channel") == "in_person"
        and (txn.get("addr1"), txn.get("addr2")) in historical_regions
    ]

    if not home_activity:
        return False

    evidence.append(
        _evidence(
            claim=(
                "The flagged card-present transaction occurs in a billing "
                "region not previously observed for the customer while "
                "historical/home-region activity continues."
            ),
            source="transactions.csv",
            ref=f"customer:{flagged['customer_id']}:out_of_region",
            entity_ids=[
                flagged["customer_id"],
                flagged["card_id"],
                flagged["id"],
            ],
        )
    )

    return True


def detect_account_takeover(flagged, customer_txns, identities, evidence):
    """
    R5/R6 documented account-takeover style signal:
    mixed-channel activity plus identity/device anomaly.
    """

    customer_channels = {
        txn.get("channel")
        for txn in customer_txns
        if txn.get("channel")
    }

    if not {"online", "in_person"}.issubset(customer_channels):
        return False

    identity = identities.get(flagged["id"]) or {}

    new_device = str(identity.get("id_15", "")).strip().lower() == "new"

    device_info = identity.get("DeviceInfo")

    unusual_device = False

    if device_info:
        other_devices = {
            str(i.get("DeviceInfo"))
            for i in identities.values()
            if i.get("DeviceInfo")
        }

        unusual_device = str(device_info) not in other_devices

    if not new_device and not unusual_device:
        return False

    evidence.append(
        _evidence(
            claim=(
                "Mixed-channel customer activity is accompanied by an "
                "identity/device anomaly consistent with the documented "
                "account-takeover pattern."
            ),
            source="transactions.csv + identity.csv",
            ref=f"customer:{flagged['customer_id']}:account_takeover",
            entity_ids=[
                flagged["customer_id"],
                flagged["card_id"],
                flagged["id"],
            ],
        )
    )

    return True


def score_case(
    flagged,
    card_txns,
    customer_txns,
    identities,
    prior_cases,
):
    """
    Deterministic benchmark investigation engine.

    IMPORTANT:
    risk_score is an investigation trigger, NOT a fraud verdict.
    """

    evidence = []
    patterns = Counter()

    risk = flagged.get("risk_score")

    # ---------------------------------------------------------
    # Risk score is contextual evidence only.
    # ---------------------------------------------------------

    if risk is not None:

        if risk >= 0.70:
            evidence.append(
                _evidence(
                    claim=(
                        f"Bank risk score is {float(risk):.2f}. "
                        "The benchmark README states that risk_score is "
                        "an investigation trigger and is not a verdict."
                    ),
                    source="transactions.csv + README.md",
                    ref=f"transaction:{flagged['id']}:risk_score",
                    entity_ids=[flagged["id"]],
                )
            )

    # ---------------------------------------------------------
    # Card testing
    # ---------------------------------------------------------

    if detect_card_testing(flagged, card_txns, evidence):
        patterns["card_testing"] += 3

    # ---------------------------------------------------------
    # CNP
    # ---------------------------------------------------------

    cnp = detect_cnp(flagged, card_txns, evidence)

    if cnp:
        patterns["card_not_present_fraud"] += 1

    # ---------------------------------------------------------
    # New device
    # ---------------------------------------------------------

    flagged_identity = identities.get(flagged["id"]) or {}

    if detect_new_device(
        flagged,
        flagged_identity,
        evidence,
    ):
        patterns["card_not_present_new_device"] += 3

    # ---------------------------------------------------------
    # Out-of-region
    # ---------------------------------------------------------

    if detect_out_of_region(
        flagged,
        customer_txns,
        evidence,
    ):
        patterns["out_of_region_use"] += 3

    # ---------------------------------------------------------
    # Account takeover
    # ---------------------------------------------------------

    if detect_account_takeover(
        flagged,
        customer_txns,
        identities,
        evidence,
    ):
        patterns["account_takeover"] += 3

    # ---------------------------------------------------------
    # Prior confirmed fraud
    # ---------------------------------------------------------

    confirmed_prior = [
        case
        for case in prior_cases
        if str(case.get("outcome", "")).lower()
        in {"confirmed_fraud", "fraud"}
    ]

    if confirmed_prior:

        evidence.append(
            _evidence(
                claim=(
                    f"{len(confirmed_prior)} prior confirmed-fraud "
                    "case(s) involve the same customer/card."
                ),
                source="closed_cases_history.csv",
                ref=f"history:{flagged['customer_id']}",
                entity_ids=[
                    case["case_id"]
                    for case in confirmed_prior[:20]
                ],
            )
        )

        for case in confirmed_prior:

            pattern = case.get("pattern")

            if pattern in DOCUMENTED_PATTERNS:
                patterns[pattern] += 1

    # ---------------------------------------------------------
    # Pattern selection
    # ---------------------------------------------------------

    if patterns:
        pattern = patterns.most_common(1)[0][0]
    else:
        pattern = "undocumented"

    # ---------------------------------------------------------
    # Fraud probability
    # ---------------------------------------------------------

    probability = 0.20

    # Risk is intentionally capped.
    if risk is not None:
        probability += min(
            0.10,
            max(0.0, (float(risk) - 0.50) * 0.20),
        )

    if patterns["card_testing"]:
        probability += 0.35

    if patterns["card_not_present_new_device"]:
        probability += 0.20

    elif patterns["card_not_present_fraud"]:
        probability += 0.15

    if patterns["out_of_region_use"]:
        probability += 0.20

    if patterns["account_takeover"]:
        probability += 0.25

    if confirmed_prior:
        probability += 0.15

    probability = min(
        0.99,
        max(0.01, probability),
    )

    # ---------------------------------------------------------
    # Legitimate recurring activity
    # ---------------------------------------------------------

    if (
        len(customer_txns) >= 5
        and not confirmed_prior
        and not patterns["card_testing"]
        and not patterns["account_takeover"]
        and not patterns["out_of_region_use"]
    ):
        probability = min(probability, 0.30)

        evidence.append(
            _evidence(
                claim=(
                    "The customer has repeated historical transaction "
                    "activity without a matching confirmed-fraud case."
                ),
                source="transactions.csv + closed_cases_history.csv",
                ref=f"customer:{flagged['customer_id']}:recurring_history",
                entity_ids=[flagged["customer_id"]],
            )
        )

    # ---------------------------------------------------------
    # Fallback evidence
    # ---------------------------------------------------------

    if not evidence:

        evidence.append(
            _evidence(
                claim=(
                    "No independent fraud evidence beyond the "
                    "investigation trigger was identified."
                ),
                source="transactions.csv",
                ref=f"transaction:{flagged['id']}:evidence",
                entity_ids=[flagged["id"]],
            )
        )

    return {
        "fraud_probability": round(probability, 3),
        "pattern": pattern,
        "evidence": evidence,
        "confirmed_prior_cases": confirmed_prior,
        "independent_evidence": independent_evidence_count(evidence),
    }