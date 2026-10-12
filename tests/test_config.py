import pytest

from bling_api_v3_auth.config import BlingConfig, storage_from_env
from bling_api_v3_auth.constants import DEFAULT_TOKEN_URL
from bling_api_v3_auth.exceptions import BlingConfigError
from bling_api_v3_auth.storage import JsonTokenStorage, MemoryTokenStorage, RedisTokenStorage

BASE_ENV = {"BLING_CLIENT_ID": "id", "BLING_CLIENT_SECRET": "secret"}


def test_from_env_defaults():
    config = BlingConfig.from_env(environ=BASE_ENV)
    assert config.client_id == "id"
    assert config.client_secret == "secret"
    assert config.enable_jwt is True
    assert config.token_url == DEFAULT_TOKEN_URL
    assert config.redirect_uri is None


def test_from_env_overrides():
    env = {
        **BASE_ENV,
        "BLING_REDIRECT_URI": "https://example.com/callback",
        "BLING_ENABLE_JWT": "false",
        "BLING_TIMEOUT": "5",
        "BLING_REFRESH_SKEW": "120",
    }
    config = BlingConfig.from_env(environ=env)
    assert config.redirect_uri == "https://example.com/callback"
    assert config.enable_jwt is False
    assert config.timeout == 5
    assert config.refresh_skew == 120


def test_legacy_skew_variable():
    config = BlingConfig.from_env(environ={**BASE_ENV, "ACCESS_TOKEN_EXPIRY_SKEW": "30"})
    assert config.refresh_skew == 30


@pytest.mark.parametrize("missing", ["BLING_CLIENT_ID", "BLING_CLIENT_SECRET"])
def test_missing_credentials(missing):
    env = dict(BASE_ENV)
    del env[missing]
    with pytest.raises(BlingConfigError, match=missing):
        BlingConfig.from_env(environ=env)


def test_invalid_bool():
    with pytest.raises(BlingConfigError, match="BLING_ENABLE_JWT"):
        BlingConfig.from_env(environ={**BASE_ENV, "BLING_ENABLE_JWT": "maybe"})


def test_repr_hides_secret():
    assert "secret" not in repr(BlingConfig("id", "secret"))


def test_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("BLING_CLIENT_ID=from-file\nBLING_CLIENT_SECRET=s\n")
    config = BlingConfig.from_env(env_file=env_file, environ={})
    assert config.client_id == "from-file"
    # real environment wins over the file
    config = BlingConfig.from_env(env_file=env_file, environ={"BLING_CLIENT_ID": "env"})
    assert config.client_id == "env"


def test_storage_from_env(tmp_path):
    json_storage = storage_from_env(environ={"BLING_TOKEN_FILE": str(tmp_path / "t.json")})
    assert isinstance(json_storage, JsonTokenStorage)
    assert json_storage.path == tmp_path / "t.json"
    assert isinstance(
        storage_from_env(environ={"BLING_TOKEN_STORAGE": "memory"}), MemoryTokenStorage
    )
    redis_storage = storage_from_env(environ={"TOKENS_STORAGE_METHOD": "redis"})
    assert isinstance(redis_storage, RedisTokenStorage)
    with pytest.raises(BlingConfigError):
        storage_from_env(environ={"BLING_TOKEN_STORAGE": "s3"})
