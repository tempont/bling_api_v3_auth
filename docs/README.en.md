# bling-api-v3-auth (English)

Lightweight OAuth 2.0 authentication for the [Bling ERP API v3](https://developer.bling.com.br),
with support for the new **JWT access tokens**. Only `requests` is required; Redis and
`.env` support are optional extras.

> Versão em português: [README.md](../README.md)

## Install

```bash
pip install bling-api-v3-auth
pip install "bling-api-v3-auth[dotenv]"   # read a .env file
pip install "bling-api-v3-auth[redis]"    # store tokens in Redis
```

Requires Python 3.10 or newer.

## Bling setup

Register an application in **Central de Extensões › Área do Integrador**
([docs](https://developer.bling.com.br/aplicativos)) and set its redirect URL and scopes.
Bling always uses the values registered in the app. Then copy the `client_id` and
`client_secret`.

## Quick start (CLI)

```bash
export BLING_CLIENT_ID=... BLING_CLIENT_SECRET=...
bling-auth login     # prints the consent URL; paste the redirect URL (or the code)
bling-auth status    # token expiry info (never prints tokens)
bling-auth token     # prints a valid access token, refreshing if needed
bling-auth revoke    # revokes at Bling and deletes local tokens
```

The authorization `code` is valid for about **1 minute** and can be used **only once**.
Reusing a code revokes the user's access.

## Library usage

```python
import requests
from bling_api_v3_auth import API_BASE_URL, BlingAuthManager

manager = BlingAuthManager.from_env()

session = requests.Session()
session.auth = manager.auth()  # Bearer token, auto-refresh, one retry on 401
session.get(f"{API_BASE_URL}/produtos", timeout=30).json()

manager.headers()  # {'Authorization': 'Bearer eyJ...', 'enable-jwt': '1'}
```

Web flow:

```python
url, state = manager.authorization_url()  # redirect the user, keep `state`
# in the callback, compare `state`, then:
manager.authorize(code)
```

Low-level client without storage: `BlingOAuthClient(config).exchange_code()`, `.refresh()` and `.revoke()`.

## Storage

- `JsonTokenStorage(path)` is the default. It writes atomically with `0600` permissions to
  `~/.config/bling_api_v3_auth/credentials.json`.
- `RedisTokenStorage(client, key=...)` works across processes and hosts. It uses a
  distributed refresh lock, and the key's TTL matches the refresh token's lifetime.
- `MemoryTokenStorage()` is meant for tests.
- Subclass `TokenStorage` (`load`, `save`, `clear`, optional `lock`) to add your own backend.

JWT access tokens are about 1,500 to 3,000 characters long, so use `TEXT` columns.

## Configuration

| Variable | Default |
| --- | --- |
| `BLING_CLIENT_ID`, `BLING_CLIENT_SECRET` | required |
| `BLING_REDIRECT_URI` | not set |
| `BLING_ENABLE_JWT` | `true` |
| `BLING_REFRESH_SKEW` | `60` seconds |
| `BLING_TIMEOUT` | `30` seconds |
| `BLING_AUTHORIZE_URL` | `https://www.bling.com.br/Api/v3/oauth/authorize` |
| `BLING_TOKEN_URL` | `https://api.bling.com.br/Api/v3/oauth/token` |
| `BLING_REVOKE_URL` | `https://api.bling.com.br/Api/v3/oauth/revoke` |
| `BLING_TOKEN_STORAGE` | `json` (`json`, `redis` or `memory`) |
| `BLING_TOKEN_FILE` | `~/.config/bling_api_v3_auth/credentials.json` |
| `BLING_REDIS_URL` / `BLING_REDIS_KEY` | `redis://localhost:6379/0` / `bling_api_v3_auth:token` |

## JWT migration

Bling has [deprecated opaque tokens](https://developer.bling.com.br/migracao-jwt) and has not
yet announced a cut-off date. It issues a JWT only when the `/oauth/token` request includes
`enable-jwt: 1`, on both the code exchange and every refresh. This library sends that header
by default.

On API calls, `enable-jwt: 1` is added only when the token is a JWT, because Bling has been
reported to reject opaque tokens sent with that header.

## Bling rules worth knowing

- Access tokens are valid for `expires_in` seconds (currently 6 h).
- Refresh tokens are valid for 30 days and are **rotated on every refresh**. The library
  serializes refreshes with locks to avoid invalidating them.
- `/oauth/token` allows 20 requests per minute per IP. Going over triggers a 60-minute block.
- The API allows 3 requests per second and 120,000 per day per account.
- When the refresh token is rejected (`invalid_grant`), the library raises
  `AuthorizationRequiredError`, and you need to authorize again.

## Errors

All exceptions inherit from `BlingApiError`:

- `BlingConfigError`: missing or invalid configuration.
- `BlingOAuthError`: an OAuth request failed. It exposes `status_code`, `error`,
  `description` and `response_body`.
- `AuthorizationRequiredError`: no tokens are stored, or Bling rejected the refresh token.

## Migrating from the old `app/` scripts

- Replace `python app/main.py` with `bling-auth login`.
- Replace `BlingApiTokenHandler` with `BlingAuthManager` (`authorize`, `refresh`,
  `get_access_token`).
- Old environment variables (`TOKENS_STORAGE_METHOD`, `REDIS_HOST_IP`, ...) still work.
- To keep using an old `credential/credentials.json`, set `BLING_TOKEN_FILE` to point at it.

## Development and release

```bash
uv sync && uv run pytest --cov && uv run ruff check . && uv run basedpyright
```

Releases are published to PyPI via Trusted Publishing when a GitHub Release `vX.Y.Z` is
created. See the Portuguese README for the one-time setup.

## License

[Unlicense](../LICENSE)
