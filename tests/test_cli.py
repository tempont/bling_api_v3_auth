import json
import sys

import pytest

import bling_api_v3_auth.oauth as oauth_module
from bling_api_v3_auth import BlingOAuthError
from bling_api_v3_auth.cli import main, parse_callback
from tests.conftest import JWT_ACCESS, add_token_response


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BLING_CLIENT_ID", "client-id")
    monkeypatch.setenv("BLING_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("BLING_TOKEN_FILE", str(tmp_path / "creds.json"))
    return tmp_path


def test_parse_callback_variants():
    assert parse_callback("abc123") == ("abc123", None)
    assert parse_callback("https://x.com/cb?code=abc&state=s1") == ("abc", "s1")
    assert parse_callback("?code=abc&state=s1") == ("abc", "s1")


def test_parse_callback_error():
    with pytest.raises(BlingOAuthError, match="access_denied"):
        parse_callback("https://x.com/cb?error=access_denied&error_description=denied&state=s")


def test_url_command(env, capsys):
    assert main(["url", "--state", "xyz"]) == 0
    out = capsys.readouterr()
    assert "client_id=client-id" in out.out
    assert "state=xyz" in out.out


def test_authorize_token_status_flow(env, mocked, capsys):
    add_token_response(mocked)
    assert main(["authorize", "https://x.com/cb?code=abc&state=s"]) == 0
    assert json.loads((env / "creds.json").read_text())["access_token"] == JWT_ACCESS

    assert main(["token"]) == 0
    assert capsys.readouterr().out.strip().endswith(JWT_ACCESS)

    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "access token:   valid" in out
    assert JWT_ACCESS not in out


def test_login_rejects_state_mismatch(env, monkeypatch, mocked):
    monkeypatch.setattr("builtins.input", lambda _prompt: "https://x.com/cb?code=abc&state=evil")
    assert main(["login"]) == 1
    assert len(mocked.calls) == 0


def test_login_success(env, monkeypatch, mocked):
    monkeypatch.setattr(oauth_module.secrets, "token_urlsafe", lambda _n: "fixed-state")
    monkeypatch.setattr("builtins.input", lambda _prompt: "?code=abc&state=fixed-state")
    add_token_response(mocked)
    assert main(["login"]) == 0


def test_missing_credentials_is_reported(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BLING_CLIENT_ID", raising=False)
    monkeypatch.delenv("BLING_CLIENT_SECRET", raising=False)
    assert main(["status"]) == 1
    assert "BLING_CLIENT_ID" in capsys.readouterr().err


def test_status_without_tokens(env):
    assert main(["status"]) == 1


@pytest.mark.parametrize("command", ["status", "token"])
@pytest.mark.parametrize(
    "redis_env",
    [{}, {"BLING_REDIS_URL": "redis://localhost:6379/0"}, {"REDIS_HOST_IP": "localhost"}],
    ids=["default-url", "explicit-url", "legacy-host"],
)
def test_missing_redis_extra_is_reported(env, monkeypatch, capsys, command, redis_env):
    monkeypatch.setenv("BLING_TOKEN_STORAGE", "redis")
    for name in ("BLING_REDIS_URL", "REDIS_HOST_IP"):
        monkeypatch.delenv(name, raising=False)
    for name, value in redis_env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setitem(sys.modules, "redis", None)

    assert main([command]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.startswith("error: ")
    assert "pip install 'bling-api-v3-auth[redis]'" in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize("command", ["status", "token"])
def test_corrupt_credentials_are_reported(env, monkeypatch, mocked, capsys, command):
    monkeypatch.setenv("BLING_TOKEN_STORAGE", "json")
    path = env / "creds.json"
    raw = '{"access_token": "private-access", "refresh_token":'
    path.write_text(raw)

    assert main([command]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.startswith("error: ")
    assert str(path) in output.err
    assert "bling-auth login" in output.err
    assert "Traceback" not in output.err
    assert "private-access" not in output.err
    assert path.read_text() == raw
    assert len(mocked.calls) == 0


def test_authorize_replaces_corrupt_credentials(env, monkeypatch, mocked):
    monkeypatch.setenv("BLING_TOKEN_STORAGE", "json")
    path = env / "creds.json"
    path.write_text('{"refresh_token":')
    add_token_response(mocked)

    assert main(["authorize", "abc"]) == 0
    assert json.loads(path.read_text())["access_token"] == JWT_ACCESS
    assert main(["status"]) == 0
