import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

from app.config import CASES_DIR
from app.db import get_connection
from app.fraud_engine import score_case
from app.policy_engine import decide_policy
from app.tigergraph_client import TigerGraphClient


class Investigator:

    def __init__(self):

        self.con = get_connection()

        self.tigergraph = TigerGraphClient()

        CASES_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

    def close(self):

        if self.con:
            self.con.close()

    # =========================================================
    # Database
    # =========================================================

    def _case_pack(self, case_id):

        row = self.con.execute(
            """
            SELECT *
            FROM case_pack
            WHERE case_id = ?
            LIMIT 1
            """,
            (case_id,),
        ).fetchone()

        if not row:
            raise ValueError(
                f"Benchmark case not found: {case_id}"
            )

        return dict(row)

    def _tx(self, transaction_id):

        row = self.con.execute(
            """
            SELECT *
            FROM transactions
            WHERE id = ?
            LIMIT 1
            """,
            (transaction_id,),
        ).fetchone()

        if not row:
            raise ValueError(
                f"Transaction not found: {transaction_id}"
            )

        return dict(row)

    def _card_txns(self, card_id):

        rows = self.con.execute(
            """
            SELECT *
            FROM transactions
            WHERE card_id = ?
            ORDER BY ts ASC
            """,
            (card_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    def _customer_txns(self, customer_id):

        rows = self.con.execute(
            """
            SELECT *
            FROM transactions
            WHERE customer_id = ?
            ORDER BY ts ASC
            """,
            (customer_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    def _identity(self, transaction_id):

        row = self.con.execute(
            """
            SELECT *
            FROM identity
            WHERE transaction_id = ?
            LIMIT 1
            """,
            (transaction_id,),
        ).fetchone()

        return dict(row) if row else {}

    def _identities_for_txns(
        self,
        transaction_ids,
    ):

        if not transaction_ids:
            return {}

        placeholders = ",".join(
            "?" for _ in transaction_ids
        )

        rows = self.con.execute(
            f"""
            SELECT *
            FROM identity
            WHERE transaction_id IN ({placeholders})
            """,
            transaction_ids,
        ).fetchall()

        return {
            int(row["transaction_id"]): dict(row)
            for row in rows
        }

    def _prior_cases(
        self,
        customer_id,
        card_id,
    ):

        rows = self.con.execute(
            """
            SELECT *
            FROM closed_cases
            WHERE customer_id = ?
               OR card_id = ?
            ORDER BY opened_at DESC
            """,
            (
                customer_id,
                card_id,
            ),
        ).fetchall()

        return [dict(row) for row in rows]

    def _similar_cases(
        self,
        pattern,
        limit=5,
    ):

        rows = self.con.execute(
            """
            SELECT
                case_id,
                customer_id,
                card_id,
                outcome,
                pattern,
                exposure_usd,
                first_fraud_txn_id
            FROM closed_cases
            WHERE pattern = ?
            ORDER BY closed_at DESC
            LIMIT ?
            """,
            (
                pattern,
                limit,
            ),
        ).fetchall()

        return [dict(row) for row in rows]

    # =========================================================
    # Connected cards
    # =========================================================

    def _connected_cards(
        self,
        customer_id,
        primary_card_id,
    ):

        rows = self.con.execute(
            """
            SELECT DISTINCT card_id
            FROM transactions
            WHERE customer_id = ?
              AND card_id IS NOT NULL
            ORDER BY card_id
            """,
            (customer_id,),
        ).fetchall()

        return [
            row["card_id"]
            for row in rows
            if row["card_id"]
            and row["card_id"] != primary_card_id
        ]

    # =========================================================
    # Connected devices
    # =========================================================

    def _connected_devices(
        self,
        transaction_ids,
    ):

        identities = self._identities_for_txns(
            transaction_ids
        )

        devices = set()

        for identity in identities.values():

            if identity.get("device_info"):
                devices.add(
                    str(identity["device_info"])
                )

            if identity.get("device_type"):
                devices.add(
                    str(identity["device_type"])
                )

        return sorted(devices)

    # =========================================================
    # Shared origin
    # =========================================================

    def _shared_origin(
        self,
        flagged,
    ):

        identity = self._identity(
            int(flagged["id"])
        )

        conditions = []

        if identity.get("device_info"):
            conditions.append(
                (
                    "device_info",
                    identity["device_info"],
                )
            )

        if identity.get("device_type"):
            conditions.append(
                (
                    "device_type",
                    identity["device_type"],
                )
            )

        if flagged.get("addr1"):
            conditions.append(
                (
                    "addr1",
                    flagged["addr1"],
                )
            )

        if flagged.get("addr2"):
            conditions.append(
                (
                    "addr2",
                    flagged["addr2"],
                )
            )

        if not conditions:
            return {
                "shared": False,
                "customers": [],
                "cards": [],
                "reasons": [],
            }

        flagged_ts = self._parse_ts(
            flagged.get("ts")
        )

        if not flagged_ts:
            return {
                "shared": False,
                "customers": [],
                "cards": [],
                "reasons": [],
            }

        start = flagged_ts - timedelta(
            days=30
        )

        end = flagged_ts + timedelta(
            days=30
        )

        rows = self.con.execute(
            """
            SELECT
                t.customer_id,
                t.card_id,
                t.addr1,
                t.addr2,
                i.device_info,
                i.device_type
            FROM transactions t
            LEFT JOIN identity i
                ON i.transaction_id = t.id
            WHERE t.customer_id != ?
              AND t.ts >= ?
              AND t.ts <= ?
            """,
            (
                flagged["customer_id"],
                start.isoformat(sep=" "),
                end.isoformat(sep=" "),
            ),
        ).fetchall()

        customers = set()
        cards = set()
        reasons = set()

        for row in rows:

            matched = False

            for field, value in conditions:

                if field == "device_info":
                    candidate = row["device_info"]

                elif field == "device_type":
                    candidate = row["device_type"]

                else:
                    candidate = row[field]

                if (
                    candidate is not None
                    and str(candidate) == str(value)
                ):
                    matched = True
                    reasons.add(
                        f"shared_{field}"
                    )

            if matched:

                if row["customer_id"]:
                    customers.add(
                        row["customer_id"]
                    )

                if row["card_id"]:
                    cards.add(
                        row["card_id"]
                    )

        return {
            "shared": bool(
                customers or cards
            ),
            "customers": sorted(customers),
            "cards": sorted(cards),
            "reasons": sorted(reasons),
        }

    # =========================================================
    # Helpers
    # =========================================================

    @staticmethod
    def _parse_ts(value):

        if not value:
            return None

        try:
            return datetime.fromisoformat(
                str(value)
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _exposure(
        transactions,
    ):

        return round(
            sum(
                abs(
                    float(
                        txn.get("amount") or 0
                    )
                )
                for txn in transactions
            ),
            2,
        )

    def _affected_transactions(
        self,
        flagged,
        card_txns,
        pattern,
    ):

        flagged_ts = self._parse_ts(
            flagged.get("ts")
        )

        if not flagged_ts:
            return [flagged]

        # Card testing
        if pattern == "card_testing":

            candidates = []

            for txn in card_txns:

                if txn.get("channel") != "online":
                    continue

                amount = abs(
                    float(
                        txn.get("amount") or 0
                    )
                )

                ts = self._parse_ts(
                    txn.get("ts")
                )

                if (
                    ts
                    and amount < 5
                    and ts <= flagged_ts
                    and flagged_ts - ts
                    <= timedelta(hours=1)
                ):
                    candidates.append(txn)

            if len(candidates) >= 3:

                return [
                    *candidates[-3:],
                    flagged,
                ]

        # CNP
        if pattern in {
            "card_not_present_fraud",
            "card_not_present_new_device",
        }:

            start = flagged_ts - timedelta(
                hours=48
            )

            end = flagged_ts + timedelta(
                hours=48
            )

            affected = [
                txn
                for txn in card_txns
                if txn.get("channel") == "online"
                and self._parse_ts(
                    txn.get("ts")
                )
                and start
                <= self._parse_ts(
                    txn["ts"]
                )
                <= end
            ]

            if not any(
                int(x["id"]) == int(flagged["id"])
                for x in affected
            ):
                affected.append(flagged)

            return sorted(
                {
                    int(x["id"]): x
                    for x in affected
                }.values(),
                key=lambda x:
                    self._parse_ts(
                        x["ts"]
                    ) or datetime.min,
            )

        if pattern == "account_takeover":

            start = flagged_ts - timedelta(
                hours=48
            )

            end = flagged_ts + timedelta(
                hours=48
            )

            affected = [
                txn
                for txn in card_txns
                if self._parse_ts(
                    txn.get("ts")
                )
                and start
                <= self._parse_ts(
                    txn["ts"]
                )
                <= end
            ]

            return sorted(
                {
                    int(x["id"]): x
                    for x in affected
                }.values(),
                key=lambda x:
                    self._parse_ts(
                        x["ts"]
                    ) or datetime.min,
            )

        return [flagged]

    # =========================================================
    # Pattern description
    # =========================================================

    @staticmethod
    def _pattern_description(pattern):

        descriptions = {

            "card_testing":
                "Multiple small online authorizations suggest "
                "card-testing activity followed by a larger purchase.",

            "card_not_present_fraud":
                "Burst of online transactions consistent with "
                "the documented card-not-present fraud pattern.",

            "card_not_present_new_device":
                "Online card-not-present activity combined with "
                "a new identity/device signal.",

            "out_of_region_use":
                "Card-present activity appears in a region not "
                "previously observed while home-region activity continues.",

            "account_takeover":
                "Mixed-channel activity combined with identity/device "
                "anomalies is consistent with possible account takeover.",

            "undocumented":
                "Suspicious activity does not cleanly match one of "
                "the documented benchmark patterns.",
        }

        return descriptions.get(
            pattern,
            descriptions["undocumented"],
        )

    # =========================================================
    # Main investigation
    # =========================================================

    def investigate(
        self,
        case_id,
    ):

        started = time.perf_counter()

        case = self._case_pack(
            case_id
        )

        flagged = self._tx(
            int(case["flagged_txn_id"])
        )

        card_txns = self._card_txns(
            flagged["card_id"]
        )

        customer_txns = self._customer_txns(
            flagged["customer_id"]
        )

        customer_txn_ids = [
            int(txn["id"])
            for txn in customer_txns
        ]

        identities = self._identities_for_txns(
            customer_txn_ids
        )

        prior_cases = self._prior_cases(
            flagged["customer_id"],
            flagged["card_id"],
        )

        # =====================================================
        # Local fraud reasoning
        # =====================================================

        score = score_case(
            flagged=flagged,
            card_txns=card_txns,
            customer_txns=customer_txns,
            identities=identities,
            prior_cases=prior_cases,
        )

        probability = float(
            score["fraud_probability"]
        )

        pattern = score["pattern"]

        evidence = score["evidence"]

        evidence_count = int(
            score["independent_evidence"]
        )

        # =====================================================
        # TigerGraph investigation
        # =====================================================

        graph_result = (
            self.tigergraph.investigate_transaction(
                transaction_id=str(
                    flagged["id"]
                ),
                customer_id=str(
                    flagged["customer_id"]
                ),
                card_id=str(
                    flagged["card_id"]
                ),
            )
        )

        graph_available = bool(
            graph_result.get(
                "graph_available"
            )
        )

        if graph_available:

            evidence.append(
                {
                    "claim": (
                        "TigerGraph contains the transaction/customer/"
                        "card entities associated with the investigation."
                    ),
                    "source": (
                        "TigerGraph CustomerTransactionGraph"
                    ),
                    "ref": (
                        f"graph:"
                        f"{flagged['id']}"
                    ),
                    "entity_ids": [
                        str(flagged["id"]),
                        str(flagged["customer_id"]),
                        str(flagged["card_id"]),
                    ],
                }
            )

            evidence_count += 1

        # =====================================================
        # Connected cards
        # =====================================================

        connected_cards = self._connected_cards(
            flagged["customer_id"],
            flagged["card_id"],
        )

        # =====================================================
        # Shared origin
        # =====================================================

        shared_origin = self._shared_origin(
            flagged
        )

        if shared_origin["shared"]:

            evidence.append(
                {
                    "claim": (
                        "Activity from another customer or card "
                        "shares an origin with the flagged activity."
                    ),
                    "source": (
                        "transactions.csv + identity.csv"
                    ),
                    "ref": (
                        f"shared-origin:"
                        f"{flagged['customer_id']}"
                    ),
                    "entity_ids": [
                        flagged["customer_id"],
                        flagged["card_id"],
                        *shared_origin["customers"],
                        *shared_origin["cards"],
                    ],
                }
            )

            evidence_count += 1

        # =====================================================
        # Affected transactions
        # =====================================================

        affected = self._affected_transactions(
            flagged,
            card_txns,
            pattern,
        )

        affected_ids = [
            int(txn["id"])
            for txn in affected
        ]

        exposure = self._exposure(
            affected
        )

        # =====================================================
        # Policy
        # =====================================================

        policy = decide_policy(
            fraud_probability=probability,
            pattern=pattern,
            exposure_usd=exposure,
            evidence_count=evidence_count,
            shared_origin=shared_origin["shared"],
            customer_response=None,
        )

        # =====================================================
        # Status
        # =====================================================

        close_no_fraud = any(
            x["action"] == "CLOSE_NO_FRAUD"
            for x in policy["final"]
        )

        analyst = any(
            x["action"] == "ESCALATE_TO_ANALYST"
            for x in policy["final"]
        )

        if probability >= 0.85:

            status = "escalated"
            verdict = "fraud"

        elif (
            probability <= 0.15
            and evidence_count >= 2
        ):

            status = "closed_legitimate"
            verdict = "legitimate"

        elif close_no_fraud:

            status = "closed_legitimate"
            verdict = "legitimate"

        elif analyst:

            status = "escalated"
            verdict = "uncertain"

        elif probability >= 0.70:

            status = "open"
            verdict = "fraud"

        else:

            status = "open"
            verdict = "uncertain"

        # =====================================================
        # Devices
        # =====================================================

        connected_devices = self._connected_devices(
            affected_ids
        )

        # =====================================================
        # Similar cases
        # =====================================================

        similar_cases = self._similar_cases(
            pattern
        )

        # =====================================================
        # SAR
        # =====================================================

        report_required = any(
            x["action"] == "FILE_REPORT"
            for x in policy["final"]
        )

        if report_required:

            dates = sorted(
                {
                    str(x["ts"])
                    for x in affected
                    if x.get("ts")
                }
            )

            sar = {
                "file": True,
                "reason": (
                    "Reporting condition met under the investigation policy."
                ),
                "narrative": (
                    f"Customer {flagged['customer_id']} and card "
                    f"{flagged['card_id']} were investigated after "
                    f"transaction {flagged['id']} triggered review. "
                    f"The detected pattern was {pattern}. "
                    f"Estimated fraud probability was "
                    f"{probability:.2f}. "
                    f"Associated exposure was "
                    f"${exposure:,.2f}."
                ),
                "subjects": [
                    flagged["customer_id"],
                    flagged["card_id"],
                ],
                "total_amount_usd": exposure,
                "activity_dates": dates,
            }

        else:

            sar = {
                "file": False,
                "reason": "",
                "narrative": "",
                "subjects": [],
                "total_amount_usd": 0.0,
                "activity_dates": [],
            }

        # =====================================================
        # Stop reason
        # =====================================================

        if probability >= 0.85:

            stop_reason = (
                "Fraud probability reached the >=0.85 stop threshold."
            )

        elif (
            probability <= 0.15
            and evidence_count >= 2
        ):

            stop_reason = (
                "Fraud probability is <=0.15 with at least "
                "two independent evidence pieces."
            )

        elif close_no_fraud:

            stop_reason = (
                "Verification resolved the activity as legitimate."
            )

        elif analyst:

            stop_reason = (
                "Evidence remains uncertain or conflicting and "
                "requires analyst review."
            )

        else:

            stop_reason = (
                "Investigation remains open because available "
                "evidence does not satisfy a terminal threshold."
            )

        # =====================================================
        # Summary
        # =====================================================

        summary = (
            f"Investigation {case_id} reviewed transaction "
            f"{flagged['id']} for customer "
            f"{flagged['customer_id']} and card "
            f"{flagged['card_id']}. "
            f"Detected pattern: {pattern}. "
            f"Estimated fraud probability: "
            f"{probability:.2f}. "
            f"Exposure: ${exposure:,.2f}. "
            f"Verdict: {verdict}."
        )

        # =====================================================
        # Case
        # =====================================================

        case_result = {

            "status": status,

            "verdict": verdict,

            "fraud_probability": probability,

            "pattern": pattern,

            "pattern_description":
                self._pattern_description(pattern),

            "affected_txn_ids":
                affected_ids,

            "first_suspicious_txn_id":
                affected_ids[0]
                if affected_ids
                else int(flagged["id"]),

            "connected_card_ids":
                connected_cards,

            "connected_device_profiles":
                connected_devices,

            "exposure_usd":
                exposure,

            "evidence":
                evidence,

            "similar_prior_cases":
                similar_cases,

            "summary":
                summary,

            "written_to_graph":
                graph_available,

            "graph_case_id":
                None,
        }

        # =====================================================
        # Tool calls
        # =====================================================

        tool_calls = [
            {
                "tool": "local_sqlite",
                "operation": "load_case",
                "case_id": case_id,
            },
            {
                "tool": "local_sqlite",
                "operation": "transaction_lookup",
                "transaction_id": int(flagged["id"]),
            },
            {
                "tool": "local_sqlite",
                "operation": "card_history",
                "card_id": flagged["card_id"],
            },
            {
                "tool": "local_sqlite",
                "operation": "customer_history",
                "customer_id": flagged["customer_id"],
            },
            {
                "tool": "fraud_engine",
                "operation": "score_case",
            },
            {
                "tool": "policy_engine",
                "operation": "decide_policy",
            },
        ]

        if graph_available:

            tool_calls.append(
                {
                    "tool": "tigergraph",
                    "operation": "investigate_transaction",
                    "graph": self.tigergraph.graph_name,
                    "transaction_id": int(flagged["id"]),
                }
            )

        # =====================================================
        # Final result
        # =====================================================

        return {

            "case_id":
                case_id,

            "case":
                case_result,

            "evidence_requests": [
                {
                    "type":
                        "customer_verification",

                    "required":
                        probability < 0.70
                        and verdict != "legitimate",

                    "status":
                        "not_sent",

                    "reason":
                        (
                            "R1: additional verification may "
                            "resolve a weak or uncertain signal."
                        ),
                }
            ],

            "next_best_actions": {
                "initial":
                    policy["initial"],

                "final":
                    policy["final"],

                "what_changed":
                    policy["what_changed"],
            },

            "sar":
                sar,

            "stop_reason":
                stop_reason,

            "tool_calls":
                tool_calls,

            "tokens": {
                "input": 0,
                "output": 0,
                "total": 0,
            },

            "latency_s":
                round(
                    time.perf_counter()
                    - started,
                    4,
                ),

            "graph": {
                "enabled":
                    graph_result.get(
                        "enabled",
                        False,
                    ),

                "available":
                    graph_available,

                "graph_name":
                    self.tigergraph.graph_name,

                "errors":
                    graph_result.get(
                        "errors",
                        [],
                    ),
            },
        }

    # =========================================================
    # Run all cases
    # =========================================================

    def run_all(self):

        rows = self.con.execute(
            """
            SELECT case_id
            FROM case_pack
            ORDER BY case_id
            """
        ).fetchall()

        generated = []

        for row in rows:

            case_id = row["case_id"]

            result = self.investigate(
                case_id
            )

            path = (
                CASES_DIR
                / f"{case_id}.json"
            )

            with path.open(
                "w",
                encoding="utf-8",
            ) as file:

                json.dump(
                    result,
                    file,
                    indent=2,
                    ensure_ascii=False,
                )

            generated.append(
                str(path)
            )

        return generated