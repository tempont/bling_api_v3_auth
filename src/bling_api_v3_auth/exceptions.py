"""Exceptions raised by :mod:`bling_api_v3_auth`."""

from __future__ import annotations


class BlingApiError(RuntimeError):
    """Base class for every error raised by this package."""


class BlingConfigError(BlingApiError, ValueError):
    """Raised when required configuration (client id, secret...) is missing or invalid."""


class BlingOAuthError(BlingApiError):
    """Raised when a Bling OAuth endpoint fails or returns an unexpected payload.

    Attributes:
        status_code: HTTP status code, or ``None`` for network/transport failures.
        error: OAuth error code returned by Bling (e.g. ``invalid_grant``), when present.
        description: Human readable error description returned by Bling, when present.
        response_body: Raw response body, useful for logging and debugging.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error: str | None = None,
        description: str | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.description = description
        self.response_body = response_body


class AuthorizationRequiredError(BlingApiError):
    """Raised when the user must (re)authorize the application in Bling.

    This happens when there are no stored tokens yet, the credentials file contains
    malformed JSON, or the stored refresh token is expired, revoked or was already
    used (Bling rotates refresh tokens).
    """
