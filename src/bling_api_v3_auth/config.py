"""Configuration objects and environment loading."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bling_api_v3_auth.constants import (
    DEFAULT_AUTHORIZE_URL,
    DEFAULT_REFRESH_SKEW,
    DEFAULT_REVOKE_URL,
    DEFAULT_TIMEOUT,
    DEFAULT_TOKEN_URL,
)
from bling_api_v3_auth.exceptions import BlingConfigError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from bling_api_v3_auth.storage import TokenStorage

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def read_env(
    env_file: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return environment variables, optionally merged with a ``.env`` file.

    Values already present in the environment take precedence over the file, and
    ``os.environ`` is never modified. Reading a file requires ``python-dotenv``
    (``pip install 'bling-api-v3-auth[dotenv]'``).
    """
    env = dict(os.environ if environ is None else environ)
    if env_file is None:
        return env
    try:
        from dotenv import dotenv_values  # noqa: PLC0415
    except ModuleNotFoundError as exc:
        msg = (
            "Reading a .env file requires python-dotenv. "
            "Install it with: pip install 'bling-api-v3-auth[dotenv]'"
        )
        raise BlingConfigError(msg) from exc
    file_values = {k: v for k, v in dotenv_values(env_file).items() if v is not None}
    return {**file_values, **env}


def _parse_bool(name: str, value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    msg = f"{name} must be a boolean (true/false), got {value!r}"
    raise BlingConfigError(msg)


def _parse_number(name: str, value: str | None, default: float) -> float:
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        msg = f"{name} must be a number, got {value!r}"
        raise BlingConfigError(msg) from exc


@dataclass(frozen=True)
class BlingConfig:
    """OAuth settings of a Bling application.

    Attributes:
        client_id: Application ``client_id`` (Bling > Central de Extensões > Área do Integrador).
        client_secret: Application ``client_secret``. Hidden from ``repr()``.
        redirect_uri: Callback URL registered in the application. Optional: when omitted
            Bling redirects to the URL registered in the app.
        enable_jwt: Send the ``enable-jwt: 1`` header so Bling issues JWT access tokens.
        authorize_url: Authorization (consent) page URL.
        token_url: Token endpoint URL.
        revoke_url: Revocation endpoint URL.
        timeout: HTTP timeout, in seconds, for OAuth requests.
        refresh_skew: Refresh the access token this many seconds before it expires.
    """

    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str | None = None
    enable_jwt: bool = True
    authorize_url: str = DEFAULT_AUTHORIZE_URL
    token_url: str = DEFAULT_TOKEN_URL
    revoke_url: str = DEFAULT_REVOKE_URL
    timeout: float = DEFAULT_TIMEOUT
    refresh_skew: int = DEFAULT_REFRESH_SKEW

    def __post_init__(self) -> None:
        if not self.client_id or not self.client_id.strip():
            msg = "client_id is required (env: BLING_CLIENT_ID)"
            raise BlingConfigError(msg)
        if not self.client_secret or not self.client_secret.strip():
            msg = "client_secret is required (env: BLING_CLIENT_SECRET)"
            raise BlingConfigError(msg)
        if self.timeout <= 0:
            msg = "timeout must be greater than zero"
            raise BlingConfigError(msg)
        if self.refresh_skew < 0:
            msg = "refresh_skew must be >= 0"
            raise BlingConfigError(msg)

    @classmethod
    def from_env(
        cls,
        *,
        env_file: str | os.PathLike[str] | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> BlingConfig:
        """Build the configuration from ``BLING_*`` environment variables.

        Supported variables: ``BLING_CLIENT_ID``, ``BLING_CLIENT_SECRET`` (required),
        ``BLING_REDIRECT_URI``, ``BLING_ENABLE_JWT``, ``BLING_AUTHORIZE_URL``,
        ``BLING_TOKEN_URL``, ``BLING_REVOKE_URL``, ``BLING_TIMEOUT`` and
        ``BLING_REFRESH_SKEW``.

        Args:
            env_file: Optional ``.env`` file to read (requires ``python-dotenv``).
            environ: Mapping used instead of ``os.environ`` (mainly for tests).

        Raises:
            BlingConfigError: If a required variable is missing or a value is invalid.
        """
        env = read_env(env_file, environ)
        skew = env.get("BLING_REFRESH_SKEW") or env.get("ACCESS_TOKEN_EXPIRY_SKEW")
        return cls(
            client_id=env.get("BLING_CLIENT_ID", ""),
            client_secret=env.get("BLING_CLIENT_SECRET", ""),
            redirect_uri=env.get("BLING_REDIRECT_URI") or None,
            enable_jwt=_parse_bool("BLING_ENABLE_JWT", env.get("BLING_ENABLE_JWT"), True),
            authorize_url=env.get("BLING_AUTHORIZE_URL") or DEFAULT_AUTHORIZE_URL,
            token_url=env.get("BLING_TOKEN_URL") or DEFAULT_TOKEN_URL,
            revoke_url=env.get("BLING_REVOKE_URL") or DEFAULT_REVOKE_URL,
            timeout=_parse_number("BLING_TIMEOUT", env.get("BLING_TIMEOUT"), DEFAULT_TIMEOUT),
            refresh_skew=int(_parse_number("BLING_REFRESH_SKEW", skew, DEFAULT_REFRESH_SKEW)),
        )


def storage_from_env(
    *,
    env_file: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> TokenStorage:
    """Build a :class:`~bling_api_v3_auth.storage.TokenStorage` from environment variables.

    ``BLING_TOKEN_STORAGE`` selects the backend: ``json`` (default), ``redis`` or
    ``memory``. JSON uses ``BLING_TOKEN_FILE``; Redis uses ``BLING_REDIS_URL`` (or the
    legacy ``REDIS_HOST_IP``/``REDIS_HOST_PORT``/``REDIS_PASSWORD``) and
    ``BLING_REDIS_KEY``. The legacy ``TOKENS_STORAGE_METHOD`` variable is still honored.
    """
    from bling_api_v3_auth.storage import (  # noqa: PLC0415
        DEFAULT_REDIS_KEY,
        JsonTokenStorage,
        MemoryTokenStorage,
        RedisTokenStorage,
    )

    env = read_env(env_file, environ)
    kind = (
        (env.get("BLING_TOKEN_STORAGE") or env.get("TOKENS_STORAGE_METHOD") or "json")
        .strip()
        .lower()
    )

    if kind == "json":
        return JsonTokenStorage(env.get("BLING_TOKEN_FILE") or None)
    if kind == "memory":
        return MemoryTokenStorage()
    if kind == "redis":
        key = env.get("BLING_REDIS_KEY") or DEFAULT_REDIS_KEY
        url = env.get("BLING_REDIS_URL")
        if url or not env.get("REDIS_HOST_IP"):
            return RedisTokenStorage(url=url, key=key)
        try:
            import redis  # noqa: PLC0415
        except ModuleNotFoundError as exc:
            msg = "Install Redis support with: pip install 'bling-api-v3-auth[redis]'"
            raise BlingConfigError(msg) from exc
        client = redis.Redis(
            host=env["REDIS_HOST_IP"],
            port=int(env.get("REDIS_HOST_PORT") or 6379),
            password=env.get("REDIS_PASSWORD") or None,
        )
        return RedisTokenStorage(client, key=key)

    msg = f"BLING_TOKEN_STORAGE must be 'json', 'redis' or 'memory', got {kind!r}"
    raise BlingConfigError(msg)
