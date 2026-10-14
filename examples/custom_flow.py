"""Authorization flow driven by your own code, with explicit configuration and storage.

Shows how to plug the library into a web app: generate the consent URL, validate
``state`` in the callback, exchange the ``code`` and later build request headers.
"""

from bling_api_v3_auth import BlingAuthManager, BlingConfig, JsonTokenStorage

config = BlingConfig(
    client_id="your-client-id",
    client_secret="your-client-secret",
)
manager = BlingAuthManager(config, JsonTokenStorage("./credential/credentials.json"))

# 1) Redirect the user to the consent page and keep `state` (e.g. in the session).
url, state = manager.authorization_url()
print("Open:", url)

# 2) In your callback handler (GET /callback?code=...&state=...):
received_state = input("state received in the callback: ")
if received_state != state:
    raise SystemExit("Invalid state (possible CSRF)")
manager.authorize(input("code received in the callback: "))  # valid for ~1 minute

# 3) Anywhere in your app:
print(manager.headers())  # {'Authorization': 'Bearer ...', 'enable-jwt': '1'}
