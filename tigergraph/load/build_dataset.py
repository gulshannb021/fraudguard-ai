import os
import json
import math
import hashlib
import pandas as pd
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "tigergraph", "load")
CASES = os.path.join(ROOT, "cases")

os.makedirs(OUT, exist_ok=True)
os.makedirs(CASES, exist_ok=True)

print("Loading case pack...")
case_pack = pd.read_csv(os.path.join(DATA, "case_pack.csv"))

print("Loading closed cases...")
closed = pd.read_csv(os.path.join(DATA, "closed_cases_history.csv"))

print("Loading identity...")
identity = pd.read_csv(os.path.join(DATA, "identity.csv"))

identity["TransactionID"] = identity["TransactionID"].astype(str)

# ---------------------------------------------------------
# CARD ID MAPPING
# ---------------------------------------------------------

print("Building card mapping...")

# A card is represented by customer + card1..card6.
# This lets us reconstruct Cxxxxx-K1/K2 style IDs.
card_cols = ["card1", "card2", "card3", "card4", "card5", "card6"]

card_map = {}
customer_card_counter = defaultdict(int)

def normalize(v):
    if pd.isna(v):
        return ""
    return str(v)

def card_fingerprint(row):
    return (
        normalize(row["customer_id"]),
        tuple(normalize(row[c]) for c in card_cols)
    )

# ---------------------------------------------------------
# OUTPUT CSV FILES
# ---------------------------------------------------------

customers = {}
cards = {}
transactions = []
devices = {}
emails = {}
regions = []

owns_edges = []
made_edges = []
device_edges = []
email_edges = []
region_edges = []

# We need transaction information for case analysis.
needed_txns = set(
    case_pack["flagged_txn_id"].astype(str).tolist()
)

for x in closed["txn_ids"].dropna():
    for tid in str(x).split("|"):
        needed_txns.add(tid.strip())

print("Processing transactions in chunks...")

txn_lookup = {}

for chunk_no, chunk in enumerate(
    pd.read_csv(
        os.path.join(DATA, "transactions.csv"),
        chunksize=100000,
        low_memory=False
    ),
    start=1
):

    print(f"Transaction chunk {chunk_no}")

    chunk["TransactionID"] = chunk["TransactionID"].astype(str)
    chunk["customer_id"] = chunk["customer_id"].astype(str)

    for _, r in chunk.iterrows():

        customer_id = r["customer_id"]

        if customer_id not in customers:
            customers[customer_id] = {
                "id": customer_id
            }

        fp = card_fingerprint(r)

        if fp not in card_map:
            customer_card_counter[customer_id] += 1
            card_id = (
                f"{customer_id}-K"
                f"{customer_card_counter[customer_id]}"
            )
            card_map[fp] = card_id

            cards[card_id] = {
                "id": card_id,
                "customer_id": customer_id,
                "card1": normalize(r["card1"]),
                "card4": normalize(r["card4"]),
                "card6": normalize(r["card6"]),
            }

            owns_edges.append({
                "customer_id": customer_id,
                "card_id": card_id
            })

        card_id = card_map[fp]

        tid = str(r["TransactionID"])

        row = {
            "id": tid,
            "customer_id": customer_id,
            "card_id": card_id,
            "amount": float(r["TransactionAmt"])
            if not pd.isna(r["TransactionAmt"]) else 0.0,
            "product": normalize(r["ProductCD"]),
            "addr1": normalize(r["addr1"]),
            "addr2": normalize(r["addr2"]),
            "email": normalize(r["P_emaildomain"]),
            "ts": normalize(r["ts"]),
            "channel": normalize(r["channel"]),
            "risk_score": float(r["risk_score"])
            if not pd.isna(r["risk_score"]) else 0.0,
        }

        transactions.append(row)

        if tid in needed_txns:
            txn_lookup[tid] = row

# ---------------------------------------------------------
# IDENTITY / DEVICE DATA
# ---------------------------------------------------------

print("Processing identity data...")

for _, r in identity.iterrows():

    tid = str(r["TransactionID"])

    if tid not in txn_lookup:
        continue

    device_info = normalize(r["DeviceInfo"])
    os_name = normalize(r["id_30"])
    browser = normalize(r["id_31"])
    screen = normalize(r["id_33"])
    new_status = normalize(r["id_15"])
    proxy = normalize(r["id_23"])

    if not any([device_info, os_name, browser, screen]):
        continue

    device_key = "|".join([
        device_info,
        os_name,
        browser,
        screen
    ])

    device_id = "DEV-" + hashlib.sha1(
        device_key.encode()
    ).hexdigest()[:12]

    devices[device_id] = {
        "id": device_id,
        "device_info": device_info,
        "os": os_name,
        "browser": browser,
        "screen": screen,
        "new_status": new_status,
        "proxy": proxy
    }

    device_edges.append({
        "transaction_id": tid,
        "device_id": device_id
    })

# ---------------------------------------------------------
# TRANSACTION EDGES
# ---------------------------------------------------------

for t in transactions:

    made_edges.append({
        "card_id": t["card_id"],
        "transaction_id": t["id"]
    })

    if t["email"]:
        email_id = "EMAIL-" + hashlib.sha1(
            t["email"].lower().encode()
        ).hexdigest()[:12]

        emails[email_id] = {
            "id": email_id,
            "domain": t["email"]
        }

        email_edges.append({
            "transaction_id": t["id"],
            "email_id": email_id
        })

    if t["addr1"]:
        region_id = "REGION-" + t["addr1"]

        regions.append({
            "id": region_id,
            "addr1": t["addr1"],
            "addr2": t["addr2"]
        })

        region_edges.append({
            "transaction_id": t["id"],
            "region_id": region_id
        })

# Deduplicate regions
region_dict = {
    x["id"]: x for x in regions
}

# ---------------------------------------------------------
# WRITE GRAPH FILES
# ---------------------------------------------------------

def write_csv(name, rows):
    if not rows:
        return

    pd.DataFrame(rows).drop_duplicates().to_csv(
        os.path.join(OUT, name),
        index=False
    )

write_csv("customers.csv", list(customers.values()))
write_csv("cards.csv", list(cards.values()))
write_csv("transactions.csv", transactions)
write_csv("devices.csv", list(devices.values()))
write_csv("emails.csv", list(emails.values()))
write_csv("regions.csv", list(region_dict.values()))

write_csv("owns.csv", owns_edges)
write_csv("made.csv", made_edges)
write_csv("device_edges.csv", device_edges)
write_csv("email_edges.csv", email_edges)
write_csv("region_edges.csv", region_edges)

# ---------------------------------------------------------
# CLOSED CASE GRAPH DATA
# ---------------------------------------------------------

closed_vertices = []

for _, r in closed.iterrows():

    closed_vertices.append({
        "id": str(r["case_id"]),
        "customer_id": normalize(r["customer_id"]),
        "card_id": normalize(r["card_id"]),
        "outcome": normalize(r["outcome"]),
        "pattern": normalize(r["pattern"]),
        "exposure": float(r["exposure_usd"])
        if not pd.isna(r["exposure_usd"]) else 0.0,
        "report_filed": normalize(r["report_filed"]),
        "notes": normalize(r["analyst_notes"])
    })

write_csv("closed_cases.csv", closed_vertices)

# Closed case -> card
case_card_edges = []

for _, r in closed.iterrows():
    if not pd.isna(r["card_id"]):
        case_card_edges.append({
            "case_id": str(r["case_id"]),
            "card_id": str(r["card_id"])
        })

write_csv("case_cards.csv", case_card_edges)

# ---------------------------------------------------------
# SAVE COMPLETE LOOKUPS FOR FAST CASE ANALYSIS
# ---------------------------------------------------------

with open(os.path.join(OUT, "txn_lookup.json"), "w") as f:
    json.dump(txn_lookup, f)

with open(os.path.join(OUT, "card_map.json"), "w") as f:
    json.dump(
        {str(k): v for k, v in card_map.items()},
        f
    )

print()
print("========================================")
print("GRAPH DATA BUILD COMPLETE")
print("========================================")
print("Customers:", len(customers))
print("Cards:", len(cards))
print("Transactions:", len(transactions))
print("Devices:", len(devices))
print("Emails:", len(emails))
print("Regions:", len(region_dict))
print("Closed cases:", len(closed))
print("========================================")