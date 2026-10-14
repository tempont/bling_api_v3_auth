"""Minimal end-to-end example.

pip install "bling-api-v3-auth[dotenv]"
export BLING_CLIENT_ID=... BLING_CLIENT_SECRET=...   # or put them in .env
bling-auth login                                      # first run only
python examples/basic_usage.py
"""

import requests

from bling_api_v3_auth import API_BASE_URL, AuthorizationRequiredError, BlingAuthManager

manager = BlingAuthManager.from_env(env_file=".env")

try:
    session = requests.Session()
    session.auth = manager.auth()  # adds the Bearer token and refreshes it when needed

    response = session.get(f"{API_BASE_URL}/produtos", params={"limite": 5}, timeout=30)
    response.raise_for_status()
    for product in response.json()["data"]:
        print(product["id"], product["nome"])
except AuthorizationRequiredError as exc:
    print(f"Authorize the application first (bling-auth login): {exc}")
