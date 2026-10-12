from urllib.parse import parse_qs, urlsplit

import pytest
import requests
import responses

from bling_api_v3_auth import BlingConfig, BlingOAuthClient, BlingOAuthError
from bling_api_v3_auth.constants import DEFAULT_REVOKE_URL, DEFAULT_TOKEN_URL
from bling_api_v3_auth.oauth import is_jwt
from tests.conftest import BASIC, JWT_ACCESS, add_token_response, token_payload


def test_token_endpoint_is_api_host():
    assert DEFAULT_TOKEN_URL == "https://api.bling.com.br/Api/v3/oauth/token"
    assert DEFAULT_REVOKE_URL == "https://api.bling.com.br/Api/v3/oauth/revoke"


def test_authorization_url(config):
    url, state = BlingOAuthClient(config).authorization_url()
    parts = urlsplit(url)
    params = parse_qs(parts.query)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == config.authorize_url
    assert params["response_type"] == ["code"]
    assert params["client_id"] == ["client-id"]
    assert params["state"] == [state]
    assert len(state) >= 16
    assert "redirect_uri" not in params


def test_authorization_url_with_state_and_redirect():
    config = BlingConfig("id", "secret", redirect_uri="https://example.com/cb")
    url, state = BlingOAuthClient(config).authorization_url("fixed")
    params = parse_qs(urlsplit(url).query)
    assert state == "fixed"
    assert params["redirect_uri"] == ["https://example.com/cb"]


def test_exchange_code_sends_expected_request(config, mocked):
    add_token_response(mocked)
    token = BlingOAuthClient(config).exchange_code(" the-code ")

    request = mocked.calls[0].request
    assert request.headers["Authorization"] == BASIC
    assert request.headers["enable-jwt"] == "1"
    assert request.headers["Accept"] == "1.0"
    assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert parse_qs(request.body) == {"grant_type": ["authorization_code"], "code": ["the-code"]}
    assert token.access_token == JWT_ACCESS
    assert token.expires_in == 21600


def test_refresh_sends_expected_request(config, mocked):
    add_token_response(mocked, token_payload(refresh="refresh-2"))
    token = BlingOAuthClient(config).refresh("refresh-1")
    body = parse_qs(mocked.calls[0].request.body)
    assert body == {"grant_type": ["refresh_token"], "refresh_token": ["refresh-1"]}
    assert mocked.calls[0].request.headers["enable-jwt"] == "1"
    assert token.refresh_token == "refresh-2"


def test_enable_jwt_can_be_disabled(mocked):
    config = BlingConfig("client-id", "client-secret", enable_jwt=False)
    add_token_response(mocked)
    BlingOAuthClient(config).refresh("r")
    assert "enable-jwt" not in mocked.calls[0].request.headers


def test_bling_error_format_is_parsed(config, mocked):
    add_token_response(
        mocked,
        {
            "error": {
                "type": "invalid_grant",
                "message": "invalid_grant",
                "description": "The authorization code has expired",
            }
        },
        status=400,
    )
    with pytest.raises(BlingOAuthError) as info:
        BlingOAuthClient(config).exchange_code("old")
    assert info.value.status_code == 400
    assert info.value.error == "invalid_grant"
    assert info.value.description == "The authorization code has expired"
    assert "invalid_grant" in str(info.value)


def test_rfc_error_format_is_parsed(config, mocked):
    add_token_response(
        mocked,
        {"error": "invalid_client", "error_description": "The client credentials are invalid"},
        status=400,
    )
    with pytest.raises(BlingOAuthError) as info:
        BlingOAuthClient(config).exchange_code("x")
    assert info.value.error == "invalid_client"
    assert info.value.description == "The client credentials are invalid"


def test_non_json_error(config, mocked):
    mocked.add(responses.POST, DEFAULT_TOKEN_URL, body="Bad gateway", status=502)
    with pytest.raises(BlingOAuthError) as info:
        BlingOAuthClient(config).refresh("r")
    assert info.value.status_code == 502
    assert info.value.error is None


def test_network_error(config, mocked):
    mocked.add(responses.POST, DEFAULT_TOKEN_URL, body=requests.ConnectionError("boom"))
    with pytest.raises(BlingOAuthError, match="Could not reach"):
        BlingOAuthClient(config).refresh("r")


def test_incomplete_token_response(config, mocked):
    add_token_response(mocked, {"access_token": "a"})
    with pytest.raises(BlingOAuthError, match="refresh_token") as info:
        BlingOAuthClient(config).refresh("r")
    assert info.value.status_code == 200


def test_revoke(config, mocked):
    mocked.add(responses.POST, DEFAULT_REVOKE_URL, status=200)
    BlingOAuthClient(config).revoke("tok", token_type_hint="refresh_token", revoke_action="logout")
    request = mocked.calls[0].request
    assert request.headers["Authorization"] == BASIC
    assert parse_qs(request.body) == {
        "token": ["tok"],
        "token_type_hint": ["refresh_token"],
        "revoke_action": ["logout"],
    }


@pytest.mark.parametrize("method", ["exchange_code", "refresh", "revoke"])
def test_empty_arguments_are_rejected(config, method):
    with pytest.raises(ValueError, match="non-empty"):
        getattr(BlingOAuthClient(config), method)("")


def test_api_headers_only_send_enable_jwt_for_jwt(config):
    client = BlingOAuthClient(config)
    assert client.api_headers(JWT_ACCESS) == {
        "Authorization": f"Bearer {JWT_ACCESS}",
        "enable-jwt": "1",
    }
    assert client.api_headers("4a9de71b8aaf91c8") == {"Authorization": "Bearer 4a9de71b8aaf91c8"}


def test_is_jwt():
    assert is_jwt(JWT_ACCESS)
    assert not is_jwt("4a9de71b8aaf91c8ebbf830888354d5479e83a01")
    assert not is_jwt("eyJonly.two")
