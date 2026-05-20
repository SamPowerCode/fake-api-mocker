import base64
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from server import create_app


def write_config(tmp_path, content):
    config = tmp_path / "mocks.yaml"
    config.write_text(content)
    return config


def basic_header(username: str, password: str) -> dict:
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


@pytest.fixture
def basic_auth_client(tmp_path):
    config = write_config(tmp_path, """
groups:
  - name: api
    prefix: /api
    auth:
      type: basic
      username: user
      password: pass
    routes:
      - path: /data
        method: GET
        status: 200
        response:
          value: 42
      - path: /data
        method: POST
        status: 201
        response:
          created: true
""")
    return TestClient(create_app(config))


@pytest.fixture
def apikey_client(tmp_path):
    config = write_config(tmp_path, """
groups:
  - name: api
    prefix: /api
    auth:
      type: apikey
      header: X-API-Key
      key: secret-key
    routes:
      - path: /items
        method: GET
        status: 200
        response:
          items: []
""")
    return TestClient(create_app(config))


@pytest.fixture
def public_client(tmp_path):
    config = write_config(tmp_path, """
groups:
  - name: api
    prefix: /api
    routes:
      - path: /health
        method: GET
        status: 200
        response:
          status: ok
""")
    return TestClient(create_app(config))


# --- Routing ---

def test_get_returns_configured_response(public_client):
    r = public_client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_404_for_unknown_route(public_client):
    r = public_client.get("/api/unknown")
    assert r.status_code == 404
    assert "No mock configured" in r.json()["detail"]


def test_405_for_wrong_method(public_client):
    r = public_client.post("/api/health")
    assert r.status_code == 405


def test_post_route_returns_correct_status(basic_auth_client):
    r = basic_auth_client.post("/api/data", headers=basic_header("user", "pass"))
    assert r.status_code == 201
    assert r.json() == {"created": True}


def test_trailing_slash_on_request_matches_route(public_client):
    r = public_client.get("/api/health/")
    assert r.status_code == 200


# --- Basic Auth ---

def test_basic_auth_success(basic_auth_client):
    r = basic_auth_client.get("/api/data", headers=basic_header("user", "pass"))
    assert r.status_code == 200
    assert r.json() == {"value": 42}


def test_basic_auth_wrong_password(basic_auth_client):
    r = basic_auth_client.get("/api/data", headers=basic_header("user", "wrong"))
    assert r.status_code == 401


def test_basic_auth_missing_header_returns_www_authenticate(basic_auth_client):
    r = basic_auth_client.get("/api/data")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Basic"


def test_basic_auth_wrong_username(basic_auth_client):
    r = basic_auth_client.get("/api/data", headers=basic_header("other", "pass"))
    assert r.status_code == 401


# --- API Key Auth ---

def test_apikey_success(apikey_client):
    r = apikey_client.get("/api/items", headers={"X-API-Key": "secret-key"})
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_apikey_wrong_value(apikey_client):
    r = apikey_client.get("/api/items", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_apikey_missing_header(apikey_client):
    r = apikey_client.get("/api/items")
    assert r.status_code == 401


# --- Public group ---

def test_public_group_requires_no_auth(public_client):
    r = public_client.get("/api/health")
    assert r.status_code == 200


# --- Longest-prefix match ---

def test_longer_prefix_takes_precedence(tmp_path):
    config = write_config(tmp_path, """
groups:
  - name: v1
    prefix: /api
    auth:
      type: apikey
      header: X-Key
      key: v1-key
    routes:
      - path: /status
        method: GET
        status: 200
        response:
          version: v1
  - name: v2
    prefix: /api/v2
    auth:
      type: apikey
      header: X-Key
      key: v2-key
    routes:
      - path: /status
        method: GET
        status: 200
        response:
          version: v2
""")
    client = TestClient(create_app(config))
    r = client.get("/api/v2/status", headers={"X-Key": "v2-key"})
    assert r.status_code == 200
    assert r.json()["version"] == "v2"

    r = client.get("/api/status", headers={"X-Key": "v1-key"})
    assert r.status_code == 200
    assert r.json()["version"] == "v1"


def test_longer_prefix_auth_not_satisfied_by_shorter_key(tmp_path):
    config = write_config(tmp_path, """
groups:
  - name: v1
    prefix: /api
    auth:
      type: apikey
      header: X-Key
      key: v1-key
    routes:
      - path: /status
        method: GET
        status: 200
        response:
          version: v1
  - name: v2
    prefix: /api/v2
    auth:
      type: apikey
      header: X-Key
      key: v2-key
    routes:
      - path: /status
        method: GET
        status: 200
        response:
          version: v2
""")
    client = TestClient(create_app(config))
    # v1 key should not work for /api/v2 routes
    r = client.get("/api/v2/status", headers={"X-Key": "v1-key"})
    assert r.status_code == 401


# --- response_file ---

def test_response_file_returns_large_payload(tmp_path):
    large = [{"id": i} for i in range(1000)]
    (tmp_path / "items.json").write_text(json.dumps(large))
    config = write_config(tmp_path, """
groups:
  - name: api
    prefix: /api
    routes:
      - path: /items
        method: GET
        status: 200
        response_file: items.json
""")
    client = TestClient(create_app(config))
    r = client.get("/api/items")
    assert r.status_code == 200
    assert len(r.json()) == 1000
