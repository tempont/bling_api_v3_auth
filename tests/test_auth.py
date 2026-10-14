import requests
import responses

from bling_api_v3_auth import BlingAuth
from bling_api_v3_auth.constants import API_BASE_URL
from tests.conftest import JWT_ACCESS, JWT_ACCESS_2, add_token_response, token_payload

PRODUCTS_URL = f"{API_BASE_URL}/produtos"


def test_requests_are_signed(manager, storage, valid_token, mocked):
    storage.save(valid_token)
    mocked.add(responses.GET, PRODUCTS_URL, json={"data": []})

    response = requests.get(PRODUCTS_URL, auth=manager.auth(), timeout=5)

    assert response.json() == {"data": []}
    headers = mocked.calls[0].request.headers
    assert headers["Authorization"] == f"Bearer {JWT_ACCESS}"
    assert headers["enable-jwt"] == "1"


def test_401_triggers_single_refresh_and_retry(manager, storage, valid_token, mocked):
    storage.save(valid_token)
    mocked.add(responses.GET, PRODUCTS_URL, status=401, json={"error": {"type": "invalid_token"}})
    add_token_response(mocked, token_payload(access=JWT_ACCESS_2, refresh="refresh-2"))
    mocked.add(responses.GET, PRODUCTS_URL, json={"data": [1]})

    session = requests.Session()
    session.auth = manager.auth()
    response = session.get(PRODUCTS_URL, timeout=5)

    assert response.status_code == 200
    assert response.json() == {"data": [1]}
    assert len(response.history) == 1
    assert mocked.calls[2].request.headers["Authorization"] == f"Bearer {JWT_ACCESS_2}"


def test_persistent_401_is_returned_after_one_retry(manager, storage, valid_token, mocked):
    storage.save(valid_token)
    mocked.add(responses.GET, PRODUCTS_URL, status=401)
    add_token_response(mocked, token_payload(access=JWT_ACCESS_2))
    mocked.add(responses.GET, PRODUCTS_URL, status=401)

    response = requests.get(PRODUCTS_URL, auth=manager.auth(), timeout=5)

    assert response.status_code == 401
    assert len(mocked.calls) == 3


def test_retry_can_be_disabled(manager, storage, valid_token, mocked):
    storage.save(valid_token)
    mocked.add(responses.GET, PRODUCTS_URL, status=401)

    response = requests.get(PRODUCTS_URL, auth=BlingAuth(manager, retry_on_401=False), timeout=5)

    assert response.status_code == 401
    assert len(mocked.calls) == 1
