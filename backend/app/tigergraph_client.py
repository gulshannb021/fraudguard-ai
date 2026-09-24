from pathlib import Path
import os
import requests
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
load_dotenv(BACKEND_DIR / ".env")

TG_HOST = os.getenv("TG_HOST", "").strip().rstrip("/")
TG_GRAPHNAME = os.getenv(
    "TG_GRAPHNAME",
    "CustomerTransactionGraph"
).strip()

TG_SECRET = os.getenv("TG_SECRET", "").strip()
TG_API_TOKEN = os.getenv("TG_API_TOKEN", "").strip()
TG_USERNAME = os.getenv("TG_USERNAME", "").strip()
TG_PASSWORD = os.getenv("TG_PASSWORD", "").strip()


class TigerGraphClient:

    def __init__(self):
        self.host = TG_HOST
        self.graph_name = TG_GRAPHNAME

        self.secret = TG_SECRET
        self.api_token = TG_API_TOKEN
        self.username = TG_USERNAME
        self.password = TG_PASSWORD

        self.enabled = bool(
            self.host and self.graph_name
        )

        self.session = requests.Session()

        if self.api_token:
            self.session.headers.update({
                "Authorization": f"Bearer {self.api_token}"
            })
        elif self.secret:
            self.session.headers.update({
                "Authorization": f"Bearer {self.secret}"
            })

        self.session.headers.update({
            "Content-Type": "application/json"
        })

    def _url(self, path):
        return f"{self.host}{path}"

    def _get(self, path, params=None):
        response = self.session.get(
            self._url(path),
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def _post(self, path, payload=None):
        response = self.session.post(
            self._url(path),
            json=payload or {},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    # ---------------------------------------------------------
    # Basic vertex lookups
    # ---------------------------------------------------------

    def get_vertex(self, vertex_type, vertex_id):

        if not self.enabled:
            raise RuntimeError(
                "TigerGraph is not configured."
            )

        path = (
            f"/restpp/graph/{self.graph_name}"
            f"/vertices/{vertex_type}/{vertex_id}"
        )

        return self._get(path)

    def get_customer(self, customer_id):
        return self.get_vertex("Customer", customer_id)

    def get_card(self, card_id):
        return self.get_vertex("Card", card_id)

    def get_transaction(self, transaction_id):
        return self.get_vertex(
            "Transaction",
            str(transaction_id)
        )

    # ---------------------------------------------------------
    # GSQL installation
    # ---------------------------------------------------------

    def run_gsql(self, query):

        if not self.enabled:
            raise RuntimeError(
                "TigerGraph is not configured."
            )

        url = self._url("/gsql/v1/gsql")

        headers = dict(self.session.headers)
        headers["Content-Type"] = "text/plain"

        response = self.session.post(
            url,
            data=query,
            headers=headers,
            timeout=60,
        )

        response.raise_for_status()

        try:
            return response.json()
        except Exception:
            return {
                "raw": response.text
            }

    def install_query_file(self, filename):

        query_path = (
            PROJECT_ROOT
            / "tigergraph"
            / "queries"
            / filename
        )

        if not query_path.exists():
            raise FileNotFoundError(
                f"GSQL file not found: {query_path}"
            )

        return self.run_gsql(
            query_path.read_text()
        )

    # ---------------------------------------------------------
    # RESTPP query execution
    # ---------------------------------------------------------

    def run_query(self, query_name, params=None):

        if not self.enabled:
            return {
                "available": False,
                "query": query_name,
                "error": "TigerGraph is not configured."
            }

        params = params or {}

        path = (
            f"/restpp/query/"
            f"{self.graph_name}/"
            f"{query_name}"
        )

        try:
            return {
                "available": True,
                "query": query_name,
                "result": self._get(
                    path,
                    params=params
                )
            }

        except Exception as exc:
            return {
                "available": False,
                "query": query_name,
                "error": str(exc)
            }

    # ---------------------------------------------------------
    # Investigation queries
    # ---------------------------------------------------------

    def query_customer_cards(self, customer_id):

        return self.run_query(
            "customer_cards",
            {
                "customer_id": str(customer_id)
            }
        )

    def query_card_transactions(self, card_id):

        return self.run_query(
            "card_transactions",
            {
                "card_id": str(card_id)
            }
        )

    def query_transaction_context(self, transaction_id):

        return self.run_query(
            "transaction_context",
            {
                "txn_id": str(transaction_id)
            }
        )

    # ---------------------------------------------------------
    # Complete graph investigation
    # ---------------------------------------------------------

    def investigate_transaction(
        self,
        transaction_id,
        customer_id="",
        card_id="",
    ):

        result = {
            "enabled": self.enabled,
            "available": False,
            "graph_name": self.graph_name,
            "transaction": None,
            "customer": None,
            "card": None,
            "customer_cards": None,
            "card_transactions": None,
            "transaction_context": None,
            "errors": [],
        }

        if not self.enabled:
            result["errors"].append(
                "TigerGraph credentials/configuration missing."
            )
            return result

        # Direct transaction lookup
        try:
            result["transaction"] = self.get_transaction(
                transaction_id
            )
        except Exception as exc:
            result["errors"].append(
                f"Transaction lookup failed: {exc}"
            )

        # Direct customer lookup
        if customer_id:
            try:
                result["customer"] = self.get_customer(
                    customer_id
                )
            except Exception as exc:
                result["errors"].append(
                    f"Customer lookup failed: {exc}"
                )

        # Direct card lookup
        if card_id:
            try:
                result["card"] = self.get_card(
                    card_id
                )
            except Exception as exc:
                result["errors"].append(
                    f"Card lookup failed: {exc}"
                )

        # Customer -> Cards
        if customer_id:
            result["customer_cards"] = (
                self.query_customer_cards(
                    customer_id
                )
            )

        # Card -> Transactions
        if card_id:
            result["card_transactions"] = (
                self.query_card_transactions(
                    card_id
                )
            )

        # Transaction -> Card -> Customer
        result["transaction_context"] = (
            self.query_transaction_context(
                transaction_id
            )
        )

        result["available"] = any([
            result["transaction"] is not None,
            result["customer"] is not None,
            result["card"] is not None,
            result["customer_cards"] is not None,
            result["card_transactions"] is not None,
            result["transaction_context"] is not None,
        ])

        return result

    # ---------------------------------------------------------
    # Case write-back
    # ---------------------------------------------------------

    def write_case(self, case_data):

        """
        Case write-back is intentionally disabled until the
        richer ClosedCase schema is deployed in TigerGraph.

        Never report a case as written when it wasn't actually
        persisted.
        """

        return {
            "written": False,
            "graph_case_id": None,
            "reason": (
                "ClosedCase write-back requires the richer "
                "FraudGuard schema to be deployed."
            )
        }

    # ---------------------------------------------------------
    # Health
    # ---------------------------------------------------------

    def health(self):

        if not self.enabled:
            return {
                "enabled": False,
                "available": False,
                "graph_name": self.graph_name,
                "error": "TigerGraph configuration missing"
            }

        return {
            "enabled": True,
            "available": True,
            "graph_name": self.graph_name
        }
