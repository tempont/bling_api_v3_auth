"""High level token management."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from bling_api_v3_auth.config import BlingConfig, storage_from_env
from bling_api_v3_auth.exceptions import AuthorizationRequiredError, BlingOAuthError
from bling_api_v3_auth.oauth import BlingOAuthClient
from bling_api_v3_auth.storage import JsonTokenStorage, TokenStorage

if TYPE_CHECKING:
    import os

    import requests

    from bling_api_v3_auth.auth import BlingAuth
    from bling_api_v3_auth.models import TokenData

# OAuth errors (compared case-insensitively) meaning the refresh token is no longer
# usable: expired, revoked, already rotated, or the user/company lost access.
_REAUTHORIZE_ERRORS = {"invalid_grant", "invalid_token", "unauthorized_error"}


class BlingAuthManager:
    """Keeps a valid Bling access token available, refreshing it when needed.

    Typical usage::

        manager = BlingAuthManager.from_env()
        url, state = manager.authorization_url()  # first run only
        manager.authorize(code)  # `code` from the redirect URL (first run only)
        headers = manager.headers()  # always valid, refreshed on demand

    Refreshes are serialized with a thread lock plus :meth:`TokenStorage.lock`,
    because Bling invalidates the previous refresh token every time a new one is
    issued.

    Args:
        config: OAuth settings.
        storage: Where tokens are kept. Defaults to :class:`JsonTokenStorage`.
        session: Optional ``requests.Session`` used for OAuth calls.
        oauth: Optional pre-built :class:`BlingOAuthClient` (overrides ``session``).
    """

    def __init__(
        self,
        config: BlingConfig,
        storage: TokenStorage | None = None,
        *,
        session: requests.Session | None = None,
        oauth: BlingOAuthClient | None = None,
    ) -> None:
        self.config = config
        self.storage = storage if storage is not None else JsonTokenStorage()
        self.oauth = oauth if oauth is not None else BlingOAuthClient(config, session=session)
        self._lock = threading.RLock()

    @classmethod
    def from_env(
        cls,
        *,
        env_file: str | os.PathLike[str] | None = None,
        storage: TokenStorage | None = None,
        session: requests.Session | None = None,
    ) -> BlingAuthManager:
        """Build a manager from ``BLING_*`` environment variables (and an optional ``.env``).

        The storage backend is chosen by ``BLING_TOKEN_STORAGE`` unless ``storage`` is given.
        """
        config = BlingConfig.from_env(env_file=env_file)
        if storage is None:
            storage = storage_from_env(env_file=env_file)
        return cls(config, storage, session=session)

    # -- authorization ---------------------------------------------------------------

    def authorization_url(self, state: str | None = None) -> tuple[str, str]:
        """Return ``(url, state)`` for the Bling consent page.

        Persist ``state`` and compare it with the ``state`` query parameter received in
        the callback before calling :meth:`authorize` (CSRF protection).
        """
        return self.oauth.authorization_url(state)

    def authorize(self, code: str) -> TokenData:
        """Exchange the authorization ``code`` for tokens and store them."""
        token = self.oauth.exchange_code(code)
        with self._lock:
            self.storage.save(token)
        return token

    # -- tokens ----------------------------------------------------------------------

    def get_token(self, *, force_refresh: bool = False) -> TokenData:
        """Return the stored tokens, refreshing them first if the access token expired.

        Raises:
            AuthorizationRequiredError: No tokens stored, or the refresh token is no
                longer accepted by Bling. Run the authorization flow again.
            BlingOAuthError: The refresh request failed for another reason.
        """
        token = self._load_or_raise()
        if not force_refresh and not token.is_access_token_expired(self.config.refresh_skew):
            return token
        return self._refresh(stale_access_token=token.access_token)

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        """Return a valid access token (see :meth:`get_token`)."""
        return self.get_token(force_refresh=force_refresh).access_token

    def refresh(self) -> TokenData:
        """Force a refresh of the stored tokens."""
        return self.get_token(force_refresh=True)

    def invalidate(self, access_token: str) -> TokenData:
        """Report that Bling rejected ``access_token`` and return fresh tokens.

        If another thread/process already replaced that token, the newer stored token
        is returned without calling Bling again.
        """
        return self._refresh(stale_access_token=access_token)

    def headers(self) -> dict[str, str]:
        """Return the headers to authenticate a Bling API v3 request."""
        return self.oauth.api_headers(self.get_access_token())

    def auth(self) -> BlingAuth:
        """Return a ``requests`` auth object bound to this manager.

        Example::

            requests.get(url, auth=manager.auth())
        """
        from bling_api_v3_auth.auth import BlingAuth  # noqa: PLC0415

        return BlingAuth(self)

    def revoke(self) -> None:
        """Revoke the stored tokens at Bling and remove them from storage."""
        with self._lock, self.storage.lock():
            token = self.storage.load()
            if token is not None:
                try:
                    self.oauth.revoke(token.refresh_token, token_type_hint="refresh_token")
                finally:
                    self.storage.clear()

    # -- internals -------------------------------------------------------------------

    def _load_or_raise(self) -> TokenData:
        token = self.storage.load()
        if token is None:
            msg = "No Bling tokens stored. Authorize the application first (authorize(code))."
            raise AuthorizationRequiredError(msg)
        return token

    def _refresh(self, *, stale_access_token: str) -> TokenData:
        with self._lock, self.storage.lock():
            current = self._load_or_raise()
            if current.access_token != stale_access_token:
                # Someone else refreshed while we were waiting for the lock.
                return current
            try:
                new_token = self.oauth.refresh(current.refresh_token)
            except BlingOAuthError as exc:
                if (exc.error or "").lower() in _REAUTHORIZE_ERRORS:
                    msg = (
                        "Bling rejected the refresh token "
                        f"({exc.error}: {exc.description or 'no description'}). "
                        "Authorize the application again."
                    )
                    raise AuthorizationRequiredError(msg) from exc
                raise
            self.storage.save(new_token)
            return new_token
