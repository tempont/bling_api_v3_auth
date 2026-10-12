"""``requests`` integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from requests.auth import AuthBase

if TYPE_CHECKING:
    import requests

    from bling_api_v3_auth.manager import BlingAuthManager

_RETRIED_ATTR = "_bling_auth_retried"
_UNAUTHORIZED = 401


class BlingAuth(AuthBase):
    """``requests`` auth handler that signs requests with a valid Bling access token.

    The token is refreshed automatically when it is about to expire. If Bling still
    answers ``401 Unauthorized`` (e.g. the token was revoked), the token is refreshed
    once and the request is retried.

    Example::

        session = requests.Session()
        session.auth = BlingAuth(manager)
        session.get("https://api.bling.com.br/Api/v3/produtos")
    """

    def __init__(self, manager: BlingAuthManager, *, retry_on_401: bool = True) -> None:
        self.manager = manager
        self.retry_on_401 = retry_on_401

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        """Add the Bling authentication headers to ``r``."""
        r.headers.update(self.manager.headers())
        if self.retry_on_401:
            r.register_hook("response", self._handle_401)
        return r

    def _handle_401(self, response: requests.Response, **kwargs: Any) -> requests.Response:
        request = response.request
        if response.status_code != _UNAUTHORIZED or getattr(request, _RETRIED_ATTR, False):
            return response

        used = str(request.headers.get("Authorization", "")).removeprefix("Bearer ").strip()
        token = self.manager.invalidate(used)

        # Release the original connection before re-sending (same approach as HTTPDigestAuth).
        _ = response.content
        response.close()

        retry = request.copy()
        retry.headers.update(self.manager.oauth.api_headers(token.access_token))
        setattr(retry, _RETRIED_ATTR, True)
        new_response = response.connection.send(retry, **kwargs)  # type: ignore[attr-defined]
        new_response.history.append(response)
        new_response.request = retry
        return new_response
