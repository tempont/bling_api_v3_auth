"""Low level client for the Bling OAuth 2.0 endpoints."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import requests

from bling_api_v3_auth._version import __version__
from bling_api_v3_auth.constants import (
    ENABLE_JWT_HEADER,
    ENABLE_JWT_VALUE,
    OAUTH_ACCEPT_HEADER,
)
from bling_api_v3_auth.exceptions import BlingOAuthError
from bling_api_v3_auth.models import TokenData

if TYPE_CHECKING:
    from bling_api_v3_auth.config import BlingConfig

USER_AGENT = f"bling-api-v3-auth/{__version__}"


def is_jwt(token: str) -> bool:
    """Return ``True`` when ``token`` looks like a JWT (``header.payload.signature``)."""
    return token.startswith("eyJ") and token.count(".") == 2  # noqa: PLR2004


def _parse_error(payload: Any) -> tuple[str | None, str | None]:
    """Extract ``(error, description)`` from Bling or RFC 6749 error payloads.

    Bling usually answers ``{"error": {"type": ..., "message": ..., "description": ...}}``
    while RFC 6749 uses ``{"error": ..., "error_description": ...}``.
    """
    if not isinstance(payload, dict):
        return None, None
    error = payload.get("error")
    if isinstance(error, dict):
        description = error.get("description") or error.get("message")
        return error.get("type"), description
    if isinstance(error, str):
        return error, payload.get("error_description") or payload.get("message")
    return None, None


class BlingOAuthClient:
    """Talks to Bling's ``/oauth/authorize``, ``/oauth/token`` and ``/oauth/revoke``.

    This class is stateless regarding tokens: it never stores anything. Use
    :class:`~bling_api_v3_auth.manager.BlingAuthManager` for storage and refresh.

    Args:
        config: OAuth settings.
        session: Optional ``requests.Session`` (connection pooling, proxies, retries...).
    """

    def __init__(self, config: BlingConfig, *, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session if session is not None else requests.Session()

    # -- URLs / headers ---------------------------------------------------------------

    def authorization_url(self, state: str | None = None) -> tuple[str, str]:
        """Build the consent page URL.

        Args:
            state: Anti-CSRF value. A random one is generated when omitted.

        Returns:
            ``(url, state)``. Keep ``state`` and compare it with the value Bling sends
            back to your redirect URI before exchanging the code.
        """
        state = state or secrets.token_urlsafe(24)
        params = {"response_type": "code", "client_id": self.config.client_id, "state": state}
        if self.config.redirect_uri:
            params["redirect_uri"] = self.config.redirect_uri
        return f"{self.config.authorize_url}?{urlencode(params)}", state

    def oauth_headers(self) -> dict[str, str]:
        """Headers sent to the token/revoke endpoints (Basic auth is added separately)."""
        headers = {
            "Accept": OAUTH_ACCEPT_HEADER,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        }
        if self.config.enable_jwt:
            headers[ENABLE_JWT_HEADER] = ENABLE_JWT_VALUE
        return headers

    def api_headers(self, access_token: str) -> dict[str, str]:
        """Headers to authenticate a Bling API v3 request with ``access_token``.

        ``enable-jwt: 1`` is only added for JWT tokens: Bling rejects opaque tokens
        sent together with that header.
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        if self.config.enable_jwt and is_jwt(access_token):
            headers[ENABLE_JWT_HEADER] = ENABLE_JWT_VALUE
        return headers

    # -- grants -----------------------------------------------------------------------

    def exchange_code(self, code: str) -> TokenData:
        """Exchange an authorization ``code`` (valid for ~1 minute, single use) for tokens."""
        if not code or not code.strip():
            msg = "code must be a non-empty string"
            raise ValueError(msg)
        return self._token_request({"grant_type": "authorization_code", "code": code.strip()})

    def refresh(self, refresh_token: str) -> TokenData:
        """Get new tokens with ``refresh_token``. Bling invalidates the old refresh token."""
        if not refresh_token:
            msg = "refresh_token must be a non-empty string"
            raise ValueError(msg)
        return self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def revoke(
        self,
        token: str,
        *,
        token_type_hint: str | None = None,
        revoke_action: str | None = None,
        revoke_target: str | None = None,
    ) -> None:
        """Revoke an access or refresh token.

        Args:
            token: Token to revoke.
            token_type_hint: ``access_token`` or ``refresh_token``.
            revoke_action: ``logout`` or ``uninstall`` (advanced revocation).
            revoke_target: ``user`` (default at Bling) or ``company``.
        """
        if not token:
            msg = "token must be a non-empty string"
            raise ValueError(msg)
        data = {"token": token}
        optional = {
            "token_type_hint": token_type_hint,
            "revoke_action": revoke_action,
            "revoke_target": revoke_target,
        }
        data.update({k: v for k, v in optional.items() if v})
        self._post(self.config.revoke_url, data)

    # -- internals --------------------------------------------------------------------

    def _token_request(self, data: dict[str, str]) -> TokenData:
        response = self._post(self.config.token_url, data)
        payload = self._json(response)
        if not isinstance(payload, dict):
            msg = "Unexpected token response from Bling: JSON object expected"
            raise BlingOAuthError(
                msg, status_code=response.status_code, response_body=response.text
            )
        try:
            return TokenData.from_response(payload)
        except BlingOAuthError as exc:
            exc.status_code = response.status_code
            exc.response_body = response.text
            raise

    def _post(self, url: str, data: dict[str, str]) -> requests.Response:
        try:
            response = self.session.post(
                url,
                data=data,
                headers=self.oauth_headers(),
                auth=(self.config.client_id, self.config.client_secret),
                timeout=self.config.timeout,
            )
        except requests.RequestException as exc:
            msg = f"Could not reach Bling OAuth endpoint: {exc}"
            raise BlingOAuthError(msg) from exc

        if not response.ok:
            error, description = _parse_error(self._json(response))
            detail = f"{error}: {description}" if error else (response.text[:200] or "no body")
            msg = f"Bling OAuth request failed (HTTP {response.status_code}) - {detail}"
            raise BlingOAuthError(
                msg,
                status_code=response.status_code,
                error=error,
                description=description,
                response_body=response.text,
            )
        return response

    @staticmethod
    def _json(response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return None
