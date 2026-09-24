import csv
import sqlite3
from pathlib import Path

from app.config import (
    DATA_DIR,
    CASE_PACK,
    IDENTITY,
    CLOSED_CASES,
    TRANSACTIONS,
    DB_PATH,
)


SCHEMA = """
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS identity;
DROP TABLE IF EXISTS closed_cases;
DROP TABLE IF EXISTS case_pack;

CREATE TABLE transactions (
    id INTEGER PRIMARY KEY,
    customer_id TEXT,
    card_id TEXT,
    amount REAL,
    product TEXT,
    addr1 TEXT,
    addr2 TEXT,
    email TEXT,
    ts TEXT,
    channel TEXT,
    risk_score REAL
);

CREATE INDEX idx_transactions_customer
ON transactions(customer_id);

CREATE INDEX idx_transactions_card
ON transactions(card_id);

CREATE INDEX idx_transactions_ts
ON transactions(ts);

CREATE TABLE identity (
    transaction_id INTEGER PRIMARY KEY,
    id_15 TEXT,
    id_16 TEXT,
    device_type TEXT,
    device_info TEXT,
    raw_json TEXT
);

CREATE TABLE closed_cases (
    case_id TEXT PRIMARY KEY,
    customer_id TEXT,
    card_id TEXT,
    opened_at TEXT,
    closed_at TEXT,
    outcome TEXT,
    pattern TEXT,
    first_fraud_txn_id INTEGER,
    txn_ids TEXT,
    n_txns INTEGER,
    exposure_usd REAL,
    connected_card_ids TEXT,
    actions_taken TEXT,
    report_filed TEXT,
    analyst_notes TEXT
);

CREATE INDEX idx_closed_customer
ON closed_cases(customer_id);

CREATE INDEX idx_closed_card
ON closed_cases(card_id);

CREATE TABLE case_pack (
    case_id TEXT PRIMARY KEY,
    opened_at TEXT,
    trigger_type TEXT,
    trigger_text TEXT,
    flagged_txn_id INTEGER,
    card_id TEXT,
    customer_id TEXT,
    risk_score REAL
);

CREATE INDEX idx_case_pack_txn
ON case_pack(flagged_txn_id);
"""


def _clean(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    if value.lower() == "nan":
        return None

    return value


def _float(value):
    value = _clean(value)

    if value is None:
        return None

    try:
        return float(value)
    except ValueError:
        return None


def _int(value):
    value = _clean(value)

    if value is None:
        return None

    try:
        return int(float(value))
    except ValueError:
        return None


def _derive_card_id(row):
    """
    The generated TigerGraph transaction file already contains
    the benchmark card_id.

    This function also supports the original transaction dataset
    if it is ever supplied.
    """

    card_id = _clean(row.get("card_id"))

    if card_id:
        return card_id

    customer_id = _clean(row.get("customer_id"))

    if not customer_id:
        return None

    # Fallback deterministic card fingerprint.
    parts = [
        _clean(row.get("card1")),
        _clean(row.get("card2")),
        _clean(row.get("card3")),
        _clean(row.get("card4")),
        _clean(row.get("card5")),
        _clean(row.get("card6")),
    ]

    fingerprint = "|".join(
        value if value is not None else ""
        for value in parts
    )

    # This fallback is only used if the reduced transaction file
    # is unavailable.
    return f"{customer_id}-K{abs(hash(fingerprint)) % 100000}"


def _derive_channel(row):
    channel = _clean(row.get("channel"))

    if channel:
        return channel

    product = _clean(row.get("ProductCD"))

    if product == "W":
        return "in_person"

    return "online"


def _load_transactions(conn):
    """
    Loads the generated reduced transaction dataset:

    tigergraph/load/transactions.csv

    Expected columns:
    id,customer_id,card_id,amount,product,addr1,addr2,
    email,ts,channel,risk_score
    """

    path = TRANSACTIONS

    if not path.exists():
        raise FileNotFoundError(
            f"Transaction dataset not found: {path}"
        )

    print(f"Loading transactions from: {path}")

    inserted = 0

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise RuntimeError(
                "transactions.csv has no header."
            )

        required = {
            "id",
            "customer_id",
            "card_id",
            "amount",
            "product",
            "addr1",
            "addr2",
            "email",
            "ts",
            "channel",
            "risk_score",
        }

        missing = required - set(reader.fieldnames)

        if missing:
            raise RuntimeError(
                "Generated transaction CSV is missing columns: "
                + ", ".join(sorted(missing))
            )

        batch = []

        for row in reader:

            batch.append(
                (
                    _int(row.get("id")),
                    _clean(row.get("customer_id")),
                    _derive_card_id(row),
                    _float(row.get("amount")),
                    _clean(row.get("product")),
                    _clean(row.get("addr1")),
                    _clean(row.get("addr2")),
                    _clean(row.get("email")),
                    _clean(row.get("ts")),
                    _derive_channel(row),
                    _float(row.get("risk_score")),
                )
            )

            if len(batch) >= 10000:

                conn.executemany(
                    """
                    INSERT OR REPLACE INTO transactions
                    (
                        id,
                        customer_id,
                        card_id,
                        amount,
                        product,
                        addr1,
                        addr2,
                        email,
                        ts,
                        channel,
                        risk_score
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )

                inserted += len(batch)
                batch.clear()

        if batch:

            conn.executemany(
                """
                INSERT OR REPLACE INTO transactions
                (
                    id,
                    customer_id,
                    card_id,
                    amount,
                    product,
                    addr1,
                    addr2,
                    email,
                    ts,
                    channel,
                    risk_score
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )

            inserted += len(batch)

    conn.commit()

    print(f"Transactions loaded: {inserted}")


def _load_identity(conn):
    if not IDENTITY.exists():
        raise FileNotFoundError(
            f"Identity dataset not found: {IDENTITY}"
        )

    print(f"Loading identity from: {IDENTITY}")

    inserted = 0

    with IDENTITY.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        batch = []

        for row in reader:

            txn_id = _int(row.get("TransactionID"))

            if txn_id is None:
                continue

            batch.append(
                (
                    txn_id,
                    _clean(row.get("id_15")),
                    _clean(row.get("id_16")),
                    _clean(row.get("DeviceType")),
                    _clean(row.get("DeviceInfo")),
                    str(
                        {
                            key: _clean(value)
                            for key, value in row.items()
                            if key.startswith("id_")
                        }
                    ),
                )
            )

            if len(batch) >= 10000:

                conn.executemany(
                    """
                    INSERT OR REPLACE INTO identity
                    (
                        transaction_id,
                        id_15,
                        id_16,
                        device_type,
                        device_info,
                        raw_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )

                inserted += len(batch)
                batch.clear()

        if batch:

            conn.executemany(
                """
                INSERT OR REPLACE INTO identity
                (
                    transaction_id,
                    id_15,
                    id_16,
                    device_type,
                    device_info,
                    raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                batch,
            )

            inserted += len(batch)

    conn.commit()

    print(f"Identity records loaded: {inserted}")


def _load_closed_cases(conn):
    if not CLOSED_CASES.exists():
        raise FileNotFoundError(
            f"Closed cases dataset not found: {CLOSED_CASES}"
        )

    print(f"Loading closed cases from: {CLOSED_CASES}")

    inserted = 0

    with CLOSED_CASES.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        batch = []

        for row in reader:

            batch.append(
                (
                    _clean(row.get("case_id")),
                    _clean(row.get("customer_id")),
                    _clean(row.get("card_id")),
                    _clean(row.get("opened_at")),
                    _clean(row.get("closed_at")),
                    _clean(row.get("outcome")),
                    _clean(row.get("pattern")),
                    _int(row.get("first_fraud_txn_id")),
                    _clean(row.get("txn_ids")),
                    _int(row.get("n_txns")),
                    _float(row.get("exposure_usd")),
                    _clean(row.get("connected_card_ids")),
                    _clean(row.get("actions_taken")),
                    _clean(row.get("report_filed")),
                    _clean(row.get("analyst_notes")),
                )
            )

            if len(batch) >= 5000:

                conn.executemany(
                    """
                    INSERT OR REPLACE INTO closed_cases
                    (
                        case_id,
                        customer_id,
                        card_id,
                        opened_at,
                        closed_at,
                        outcome,
                        pattern,
                        first_fraud_txn_id,
                        txn_ids,
                        n_txns,
                        exposure_usd,
                        connected_card_ids,
                        actions_taken,
                        report_filed,
                        analyst_notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )

                inserted += len(batch)
                batch.clear()

        if batch:

            conn.executemany(
                """
                INSERT OR REPLACE INTO closed_cases
                (
                    case_id,
                    customer_id,
                    card_id,
                    opened_at,
                    closed_at,
                    outcome,
                    pattern,
                    first_fraud_txn_id,
                    txn_ids,
                    n_txns,
                    exposure_usd,
                    connected_card_ids,
                    actions_taken,
                    report_filed,
                    analyst_notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )

            inserted += len(batch)

    conn.commit()

    print(f"Closed cases loaded: {inserted}")


def _load_case_pack(conn):
    if not CASE_PACK.exists():
        raise FileNotFoundError(
            f"Case pack not found: {CASE_PACK}"
        )

    print(f"Loading case pack from: {CASE_PACK}")

    with CASE_PACK.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        rows = []

        for row in reader:

            rows.append(
                (
                    _clean(row.get("case_id")),
                    _clean(row.get("opened_at")),
                    _clean(row.get("trigger_type")),
                    _clean(row.get("trigger_text")),
                    _int(row.get("flagged_txn_id")),
                    _clean(row.get("card_id")),
                    _clean(row.get("customer_id")),
                    _float(row.get("risk_score")),
                )
            )

    conn.executemany(
        """
        INSERT OR REPLACE INTO case_pack
        (
            case_id,
            opened_at,
            trigger_type,
            trigger_text,
            flagged_txn_id,
            card_id,
            customer_id,
            risk_score
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    conn.commit()

    print(f"Benchmark cases loaded: {len(rows)}")


def initialize_database(force=False):
    """
    Build the local investigation database.

    Uses the generated TigerGraph transaction CSV because it
    contains the benchmark-compatible card_id and reduced fields.
    """

    if force and DB_PATH.exists():
        DB_PATH.unlink()

    first_build = not DB_PATH.exists()

    conn = sqlite3.connect(DB_PATH)

    conn.row_factory = sqlite3.Row

    if first_build:

        print("Creating FraudGuard SQLite database...")

        conn.executescript(SCHEMA)

        _load_transactions(conn)
        _load_identity(conn)
        _load_closed_cases(conn)
        _load_case_pack(conn)

        print("FraudGuard database initialized.")

    return conn


def get_connection():
    return initialize_database()