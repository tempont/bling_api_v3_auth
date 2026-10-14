"""Lightweight OAuth 2.0 (JWT) authentication for the Bling ERP API v3."""

from bling_api_v3_auth._version import __version__
from bling_api_v3_auth.auth import BlingAuth
from bling_api_v3_auth.config import BlingConfig, storage_from_env
from bling_api_v3_auth.constants import API_BASE_URL
from bling_api_v3_auth.exceptions import (
    AuthorizationRequiredError,
    BlingApiError,
    BlingConfigError,
    BlingOAuthError,
)
from bling_api_v3_auth.manager import BlingAuthManager
from bling_api_v3_auth.models import TokenData
from bling_api_v3_auth.oauth import BlingOAuthClient
from bling_api_v3_auth.storage import (
    JsonTokenStorage,
    MemoryTokenStorage,
    RedisTokenStorage,
    TokenStorage,
)

__all__ = [
    "API_BASE_URL",
    "AuthorizationRequiredError",
    "BlingApiError",
    "BlingAuth",
    "BlingAuthManager",
    "BlingConfig",
    "BlingConfigError",
    "BlingOAuthClient",
    "BlingOAuthError",
    "JsonTokenStorage",
    "MemoryTokenStorage",
    "RedisTokenStorage",
    "TokenData",
    "TokenStorage",
    "__version__",
    "storage_from_env",
]
