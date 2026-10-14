"""Bling API v3 OAuth endpoints and defaults.

Reference: https://developer.bling.com.br/aplicativos and
https://developer.bling.com.br/migracao-jwt
"""

DEFAULT_AUTHORIZE_URL = "https://www.bling.com.br/Api/v3/oauth/authorize"
DEFAULT_TOKEN_URL = "https://api.bling.com.br/Api/v3/oauth/token"
DEFAULT_REVOKE_URL = "https://api.bling.com.br/Api/v3/oauth/revoke"
API_BASE_URL = "https://api.bling.com.br/Api/v3"

# Bling only issues JWT access tokens when this header is sent on the token
# requests (authorization_code and refresh_token). Opaque tokens are deprecated.
ENABLE_JWT_HEADER = "enable-jwt"
ENABLE_JWT_VALUE = "1"

# Value used by Bling's official examples for the OAuth endpoints.
OAUTH_ACCEPT_HEADER = "1.0"

DEFAULT_ACCESS_TOKEN_LIFETIME = 6 * 60 * 60  # 6 hours, as returned in ``expires_in``
DEFAULT_REFRESH_TOKEN_LIFETIME = 30 * 24 * 60 * 60  # 30 days
DEFAULT_REFRESH_SKEW = 60  # refresh this many seconds before the access token expires
DEFAULT_TIMEOUT = 30.0
