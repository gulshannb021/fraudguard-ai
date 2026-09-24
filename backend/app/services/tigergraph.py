import os
import requests


TG_HOST = os.getenv("TIGERGRAPH_HOST", "")
TG_GRAPH = os.getenv("TIGERGRAPH_GRAPH", "FraudGuard")
TG_TOKEN = os.getenv("TIGERGRAPH_TOKEN", "")


def _headers():
    headers = {
        "Content-Type": "application/json"
    }

    if TG_TOKEN:
        headers["Authorization"] = f"Bearer {TG_TOKEN}"

    return headers


def run_query(query_name: str, params: dict):

    if not TG_HOST:
        return {
            "error": True,
            "message": "TigerGraph is not configured"
        }

    url = (
        f"{TG_HOST.rstrip('/')}"
        f"/query/{TG_GRAPH}/{query_name}"
    )

    response = requests.post(
        url,
        json=params,
        headers=_headers(),
        timeout=30
    )

    response.raise_for_status()

    return response.json()


def get_transaction_context(transaction_id: str):

    return run_query(
        "transaction_context",
        {"txn_id": transaction_id}
    )


def get_card_history(card_id: str):

    return run_query(
        "card_history",
        {"card_id": card_id}
    )


def get_device_neighbors(transaction_id: str):

    return run_query(
        "device_neighbors",
        {"txn_id": transaction_id}
    )