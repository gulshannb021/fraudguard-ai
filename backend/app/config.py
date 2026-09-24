from pathlib import Path
import os


ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = ROOT / "data"

CASE_PACK = DATA_DIR / "case_pack.csv"

TRANSACTIONS = (
    ROOT
    / "tigergraph"
    / "load"
    / "transactions.csv"
)

IDENTITY = DATA_DIR / "identity.csv"

CLOSED_CASES = (
    DATA_DIR
    / "closed_cases_history.csv"
)

CASES_DIR = ROOT / "cases"

DB_PATH = ROOT / "fraudguard.sqlite3"


# =========================================================
# TigerGraph
# =========================================================

TG_HOST = os.getenv(
    "TG_HOST",
    "",
)

TG_SECRET = os.getenv(
    "TG_SECRET",
    "",
)

TG_GRAPHNAME = os.getenv(
    "TG_GRAPHNAME",
    "CustomerTransactionGraph",
)