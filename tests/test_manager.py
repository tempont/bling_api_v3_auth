import threading
from urllib.parse import parse_qs

import pytest
import requests
import responses

from bling_api_v3_auth import (
    AuthorizationRequiredError,
    BlingAuthManager,
    BlingOAuthError,
    MemoryTokenStorage,
)
from bling_api_v3_auth.constants import DEFAULT_REVOKE_URL
from tests.conftest import JWT_ACCESS, JWT_ACCESS_2, add_token_response, token_payload


def test_authorize_stores_tokens(manager, storage, mocked):
    add_token_response(mocked)
    token = manager.authorize("code")
    assert storage.load() == token


def test_get_access_token_without_tokens(manager):
    with pytest.raises(AuthorizationRequiredError):
        manager.get_access_token()


def test_valid_token_is_returned_without_http(manager, storage, valid_token, mocked):
    storage.save(valid_token)
    assert manager.get_access_token() == JWT_ACCESS
    assert len(mocked.calls) == 0


def test_expired_token_is_refreshed_and_rotated(manager, storage, expired_token, mocked):
    storage.save(expired_token)
    add_token_response(mocked, token_payload(access=JWT_ACCESS_2, refresh="refresh-2"))

    assert manager.get_access_token() == JWT_ACCESS_2
    assert parse_qs(mocked.calls[0].request.body)["refresh_token"] == ["refresh-1"]
    stored = storage.load()
    assert stored is not None
    assert stored.refresh_token == "refresh-2"


def test_token_inside_skew_is_refreshed(manager, storage, valid_token, mocked):
    storage.save(
        type(valid_token)(
            access_token=JWT_ACCESS,
            refresh_token="refresh-1",
            expires_in=30,
        )
    )
    add_token_response(mocked, token_payload(access=JWT_ACCESS_2))
    assert manager.get_access_token() == JWT_ACCESS_2


def test_force_refresh(manager, storage, valid_token, mocked):
    storage.save(valid_token)
    add_token_response(mocked, token_payload(access=JWT_ACCESS_2))
    assert manager.refresh().access_token == JWT_ACCESS_2


def test_invalid_grant_requires_reauthorization(manager, storage, expired_token, mocked):
    storage.save(expired_token)
    add_token_response(
        mocked,
        {"error": {"type": "invalid_grant", "description": "Invalid refresh token"}},
        status=400,
    )
    with pytest.raises(AuthorizationRequiredError, match="invalid_grant"):
        manager.get_access_token()
    assert storage.load() == expired_token  # nothing is lost


def test_other_errors_propagate(manager, storage, expired_token, mocked):
    storage.save(expired_token)
    add_token_response(mocked, {"error": "invalid_client"}, status=400)
    with pytest.raises(BlingOAuthError) as info:
        manager.get_access_token()
    assert not isinstance(info.value, AuthorizationRequiredError)


def test_invalidate_skips_refresh_when_token_already_replaced(
    manager, storage, valid_token, mocked
):
    storage.save(valid_token)
    assert manager.invalidate("some-older-token") == valid_token
    assert len(mocked.calls) == 0


def test_concurrent_refreshes_hit_bling_once(config, expired_token, mocked):
    storage = MemoryTokenStorage(expired_token)
    manager = BlingAuthManager(config, storage)
    add_token_response(mocked, token_payload(access=JWT_ACCESS_2, refresh="refresh-2"))

    results = []
    barrier = threading.Barrier(5)

    def worker():
        barrier.wait()
        results.append(manager.get_access_token())

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results == [JWT_ACCESS_2] * 5
    assert len(mocked.calls) == 1


def test_headers(manager, storage, valid_token):
    storage.save(valid_token)
    assert manager.headers() == {"Authorization": f"Bearer {JWT_ACCESS}", "enable-jwt": "1"}


def test_revoke_clears_storage(manager, storage, valid_token, mocked):
    storage.save(valid_token)
    mocked.add(responses.POST, DEFAULT_REVOKE_URL, status=200)
    manager.revoke()
    assert storage.load() is None
    assert parse_qs(mocked.calls[0].request.body)["token"] == ["refresh-1"]


def test_revoke_without_tokens_is_noop(manager, mocked):
    manager.revoke()
    assert len(mocked.calls) == 0


def test_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BLING_CLIENT_ID", "id")
    monkeypatch.setenv("BLING_CLIENT_SECRET", "secret")
    monkeypatch.setenv("BLING_TOKEN_FILE", str(tmp_path / "creds.json"))
    manager = BlingAuthManager.from_env(session=requests.Session())
    assert manager.config.client_id == "id"
    assert manager.storage.path == tmp_path / "creds.json"  # type: ignore[attr-defined]
