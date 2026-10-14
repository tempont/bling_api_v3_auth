import base64
import time

import pytest
import responses

from bling_api_v3_auth import BlingAuthManager, BlingConfig, MemoryTokenStorage, TokenData
from bling_api_v3_auth.constants import DEFAULT_TOKEN_URL

JWT_ACCESS = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
JWT_ACCESS_2 = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIyIn0.c2lnbmF0dXJlMg"
BASIC = "Basic " + base64.b64encode(b"client-id:client-secret").decode()


def token_payload(access=JWT_ACCESS, refresh="refresh-1", expires_in=21600):
    return {
        "access_token": access,
        "expires_in": expires_in,
        "token_type": "Bearer",
        "scope": "98309 318257570",
        "refresh_token": refresh,
    }


@pytest.fixture
def config():
    return BlingConfig(client_id="client-id", client_secret="client-secret")


@pytest.fixture
def mocked():
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture
def storage():
    return MemoryTokenStorage()


@pytest.fixture
def manager(config, storage):
    return BlingAuthManager(config, storage)


@pytest.fixture
def expired_token():
    return TokenData(
        access_token=JWT_ACCESS,
        refresh_token="refresh-1",
        expires_in=21600,
        obtained_at=time.time() - 30000,
    )


@pytest.fixture
def valid_token():
    return TokenData(access_token=JWT_ACCESS, refresh_token="refresh-1", expires_in=21600)


def add_token_response(mocked, payload=None, status=200):
    mocked.add(
        responses.POST,
        DEFAULT_TOKEN_URL,
        json=payload if payload is not None else token_payload(),
        status=status,
    )
