"""Token data model."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from bling_api_v3_auth.constants import (
    DEFAULT_ACCESS_TOKEN_LIFETIME,
    DEFAULT_REFRESH_TOKEN_LIFETIME,
)
from bling_api_v3_auth.exceptions import BlingOAuthError

if TYPE_CHECKING:
    from collections.abc import Mapping


def _as_int(value: object, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class TokenData:
    """Access/refresh token pair returned by Bling, plus the time it was obtained.

    Token values are hidden from ``repr()`` so they do not leak into logs.
    """

    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_in: int = DEFAULT_ACCESS_TOKEN_LIFETIME
    token_type: str = "Bearer"
    scope: str | None = None
    obtained_at: float = field(default_factory=time.time)
    refresh_token_expires_in: int = DEFAULT_REFRESH_TOKEN_LIFETIME

    @property
    def expires_at(self) -> float:
        """Unix timestamp at which the access token expires."""
        return self.obtained_at + self.expires_in

    @property
    def refresh_token_expires_at(self) -> float:
        """Unix timestamp at which the refresh token expires."""
        return self.obtained_at + self.refresh_token_expires_in

    def is_access_token_expired(self, skew: int = 0, *, now: float | None = None) -> bool:
        """Return ``True`` when the access token is expired or expires within ``skew`` seconds."""
        current = time.time() if now is None else now
        return current >= self.expires_at - skew

    def is_refresh_token_expired(self, *, now: float | None = None) -> bool:
        """Return ``True`` when the refresh token is past its (estimated) lifetime."""
        current = time.time() if now is None else now
        return current >= self.refresh_token_expires_at

    @classmethod
    def from_response(
        cls,
        payload: Mapping[str, Any],
        *,
        obtained_at: float | None = None,
    ) -> TokenData:
        """Build an instance from a Bling ``/oauth/token`` JSON response.

        Raises:
            BlingOAuthError: If ``access_token`` or ``refresh_token`` are missing.
        """
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not access_token:
            msg = "Bling token response is missing 'access_token'"
            raise BlingOAuthError(msg)
        if not isinstance(refresh_token, str) or not refresh_token:
            msg = "Bling token response is missing 'refresh_token'"
            raise BlingOAuthError(msg)
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=_as_int(payload.get("expires_in"), DEFAULT_ACCESS_TOKEN_LIFETIME),
            token_type=str(payload.get("token_type") or "Bearer"),
            scope=payload.get("scope") or None,
            obtained_at=time.time() if obtained_at is None else obtained_at,
            refresh_token_expires_in=_as_int(
                payload.get("refresh_token_expires_in"), DEFAULT_REFRESH_TOKEN_LIFETIME
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict (includes the token values)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TokenData | None:
        """Deserialize from :meth:`to_dict` output.

        Also accepts the flat ``credentials.json`` layout written by versions of this
        project prior to 1.0 (``access_token_expires_in``, ``access_token_obtained_at``...).
        Returns ``None`` when the data does not contain both tokens.
        """
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        if not access_token or not refresh_token:
            return None

        if "access_token_obtained_at" in data:  # legacy (< 1.0) layout
            return cls(
                access_token=str(access_token),
                refresh_token=str(refresh_token),
                expires_in=_as_int(
                    data.get("access_token_expires_in"), DEFAULT_ACCESS_TOKEN_LIFETIME
                ),
                obtained_at=float(_as_int(data.get("access_token_obtained_at"), 0)),
                refresh_token_expires_in=_as_int(
                    data.get("refresh_token_expires_in"), DEFAULT_REFRESH_TOKEN_LIFETIME
                ),
            )

        return cls(
            access_token=str(access_token),
            refresh_token=str(refresh_token),
            expires_in=_as_int(data.get("expires_in"), DEFAULT_ACCESS_TOKEN_LIFETIME),
            token_type=str(data.get("token_type") or "Bearer"),
            scope=data.get("scope") or None,
            obtained_at=float(data.get("obtained_at") or 0),
            refresh_token_expires_in=_as_int(
                data.get("refresh_token_expires_in"), DEFAULT_REFRESH_TOKEN_LIFETIME
            ),
        )
