import pytest

from bling_api_v3_auth.exceptions import BlingOAuthError
from bling_api_v3_auth.models import TokenData


def test_from_response_parses_bling_payload():
    token = TokenData.from_response(
        {
            "access_token": "jwt.access",
            "expires_in": 21600,
            "token_type": "Bearer",
            "scope": "98309 5990556",
            "refresh_token": "refresh",
        },
        obtained_at=1000.0,
    )
    assert token.access_token == "jwt.access"
    assert token.refresh_token == "refresh"
    assert token.expires_in == 21600
    assert token.scope == "98309 5990556"
    assert token.expires_at == 1000.0 + 21600


def test_from_response_uses_defaults_for_missing_lifetimes():
    token = TokenData.from_response({"access_token": "a", "refresh_token": "r"})
    assert token.expires_in > 0
    assert token.refresh_token_expires_in == 30 * 24 * 3600


@pytest.mark.parametrize("missing", ["access_token", "refresh_token"])
def test_from_response_requires_tokens(missing):
    payload = {"access_token": "a", "refresh_token": "r", "expires_in": 10}
    del payload[missing]
    with pytest.raises(BlingOAuthError, match=missing):
        TokenData.from_response(payload)


def test_expiration_with_skew():
    token = TokenData("a", "r", expires_in=100, obtained_at=0)
    assert not token.is_access_token_expired(now=39)
    assert not token.is_access_token_expired(skew=60, now=39)
    assert token.is_access_token_expired(skew=60, now=40)
    assert token.is_access_token_expired(now=100)


def test_refresh_token_expiration():
    token = TokenData("a", "r", obtained_at=0, refresh_token_expires_in=50)
    assert not token.is_refresh_token_expired(now=49)
    assert token.is_refresh_token_expired(now=50)


def test_repr_hides_tokens():
    text = repr(TokenData("secret-access", "secret-refresh"))
    assert "secret-access" not in text
    assert "secret-refresh" not in text


def test_dict_roundtrip():
    token = TokenData("a", "r", expires_in=10, scope="s", obtained_at=5.0)
    assert TokenData.from_dict(token.to_dict()) == token


def test_from_dict_reads_legacy_layout():
    legacy = {
        "access_token": "a",
        "access_token_expires_in": 3600,
        "access_token_obtained_at": 1700000000,
        "refresh_token": "r",
        "refresh_token_expires_in": 2592000,
        "refresh_token_obtained_at": 1700000000,
    }
    token = TokenData.from_dict(legacy)
    assert token is not None
    assert token.access_token == "a"
    assert token.expires_at == 1700000000 + 3600


def test_from_dict_returns_none_for_empty_legacy_file():
    empty = {"access_token": "", "refresh_token": "", "access_token_obtained_at": ""}
    assert TokenData.from_dict(empty) is None
