import json
import os
import stat
import sys
import time

import fakeredis
import pytest

from bling_api_v3_auth.exceptions import AuthorizationRequiredError, BlingConfigError
from bling_api_v3_auth.models import TokenData
from bling_api_v3_auth.storage import JsonTokenStorage, MemoryTokenStorage, RedisTokenStorage


@pytest.fixture
def token():
    return TokenData("access", "refresh", expires_in=21600, obtained_at=time.time())


def test_memory_storage(token):
    storage = MemoryTokenStorage()
    assert storage.load() is None
    storage.save(token)
    assert storage.load() == token
    storage.clear()
    assert storage.load() is None


def test_json_storage_roundtrip(tmp_path, token):
    path = tmp_path / "nested" / "credentials.json"
    storage = JsonTokenStorage(path)
    assert storage.load() is None
    storage.save(token)
    assert storage.load() == token
    assert json.loads(path.read_text())["access_token"] == "access"
    storage.clear()
    assert not path.exists()
    storage.clear()  # idempotent


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_json_storage_permissions(tmp_path, token):
    path = tmp_path / "credentials.json"
    JsonTokenStorage(path).save(token)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_json_storage_leaves_no_temp_files(tmp_path, token):
    storage = JsonTokenStorage(tmp_path / "credentials.json")
    storage.save(token)
    storage.save(token)
    assert [p.name for p in tmp_path.iterdir()] == ["credentials.json"]


def test_json_storage_reads_legacy_file(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(
        json.dumps(
            {
                "access_token": "old",
                "access_token_expires_in": 3600,
                "access_token_obtained_at": 1,
                "refresh_token": "old-refresh",
                "refresh_token_expires_in": 2592000,
                "refresh_token_obtained_at": 1,
            }
        )
    )
    loaded = JsonTokenStorage(path).load()
    assert loaded is not None
    assert loaded.refresh_token == "old-refresh"


def test_json_storage_empty_file(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text("")
    assert JsonTokenStorage(path).load() is None


def test_json_storage_corrupt_file_requires_authorization(tmp_path):
    path = tmp_path / "credentials.json"
    raw = '{"access_token": "private-access", "refresh_token":'
    path.write_text(raw)
    with pytest.raises(AuthorizationRequiredError, match="bling-auth login") as error:
        JsonTokenStorage(path).load()
    assert isinstance(error.value.__cause__, json.JSONDecodeError)
    assert str(path) in str(error.value)
    assert "private-access" not in str(error.value)
    assert path.read_text() == raw


def test_redis_storage_missing_extra_is_config_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "redis", None)
    with pytest.raises(BlingConfigError, match=r"bling-api-v3-auth\[redis\]"):
        RedisTokenStorage()


def test_redis_storage(token):
    client = fakeredis.FakeRedis()
    storage = RedisTokenStorage(client, key="test:token")
    assert storage.load() is None
    storage.save(token)
    assert storage.load() == token
    ttl = client.ttl("test:token")
    assert 0 < ttl <= token.refresh_token_expires_in
    with storage.lock():
        assert client.exists("test:token:lock")
    storage.clear()
    assert storage.load() is None
