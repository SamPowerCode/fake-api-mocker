# Fake API Mocker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local FastAPI mock server that returns predetermined JSON responses from a YAML config, with per-route-group Basic Auth and API Key authentication.

**Architecture:** Single `server.py` using a catch-all FastAPI route. At startup, `_load_config` parses `mocks.yaml` into a route lookup dict and an auth map. The catch-all handler does longest-prefix group matching, auth validation, then route lookup. Tests use FastAPI's `TestClient` with per-test configs created in `tmp_path`.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, PyYAML, pytest, httpx (via TestClient), managed with `uv`.

---

## File Map

| File | Purpose |
|---|---|
| `pyproject.toml` | uv project config, runtime + dev dependencies |
| `server.py` | `_load_config`, `_check_auth`, `create_app`, module-level `app` |
| `mocks.yaml` | Example config (required for module-level `app` at runtime) |
| `responses/transactions.json` | Example large response file referenced by `mocks.yaml` |
| `tests/test_config.py` | Unit tests for `_load_config` |
| `tests/test_server.py` | Integration tests via `TestClient(create_app(...))` |

---

### Task 1: Initialize uv project

**Files:**
- Create: `pyproject.toml`
- Create: `tests/` (empty directory)

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "fake-api-mocker"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pyyaml>=6.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "httpx>=0.27.0",
]
```

- [ ] **Step 2: Initialize the project and install dependencies**

Run: `uv sync --dev`
Expected: `uv.lock` created, `.venv/` created, no errors.

- [ ] **Step 3: Create tests directory**

Run: `mkdir tests`

- [ ] **Step 4: Commit**

```bash
git init
git add pyproject.toml uv.lock
git commit -m "chore: initialize uv project"
```

---

### Task 2: Config loading

**Files:**
- Create: `tests/test_config.py`
- Create: `server.py` (partial — `_load_config` only)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config.py`:

```python
import json
import pytest
from pathlib import Path
from server import _load_config


def write_config(tmp_path, content):
    config = tmp_path / "mocks.yaml"
    config.write_text(content)
    return config


def test_inline_response_loaded(tmp_path):
    config = write_config(tmp_path, """
groups:
  - name: test
    prefix: /api
    routes:
      - path: /users
        method: GET
        status: 200
        response:
          id: 1
          name: alice
""")
    route_map, _, _ = _load_config(config)
    assert ("GET", "/api/users") in route_map
    status, body = route_map[("GET", "/api/users")]
    assert status == 200
    assert body == {"id": 1, "name": "alice"}


def test_response_file_loaded(tmp_path):
    large = [{"id": i} for i in range(1000)]
    (tmp_path / "large.json").write_text(json.dumps(large))
    config = write_config(tmp_path, """
groups:
  - name: test
    prefix: /api
    routes:
      - path: /items
        method: GET
        status: 200
        response_file: large.json
""")
    route_map, _, _ = _load_config(config)
    status, body = route_map[("GET", "/api/items")]
    assert status == 200
    assert len(body) == 1000


def test_missing_response_file_exits(tmp_path):
    config = write_config(tmp_path, """
groups:
  - name: test
    prefix: /api
    routes:
      - path: /items
        method: GET
        status: 200
        response_file: missing.json
""")
    with pytest.raises(SystemExit):
        _load_config(config)


def test_both_response_fields_exits(tmp_path):
    config = write_config(tmp_path, """
groups:
  - name: test
    prefix: /api
    routes:
      - path: /items
        method: GET
        status: 200
        response:
          ok: true
        response_file: something.json
""")
    with pytest.raises(SystemExit):
        _load_config(config)


def test_neither_response_field_exits(tmp_path):
    config = write_config(tmp_path, """
groups:
  - name: test
    prefix: /api
    routes:
      - path: /items
        method: GET
        status: 200
""")
    with pytest.raises(SystemExit):
        _load_config(config)


def test_trailing_slashes_normalized(tmp_path):
    config = write_config(tmp_path, """
groups:
  - name: test
    prefix: /api/
    routes:
      - path: /users/
        method: GET
        status: 200
        response: {}
""")
    route_map, _, _ = _load_config(config)
    assert ("GET", "/api/users") in route_map


def test_method_normalized_to_uppercase(tmp_path):
    config = write_config(tmp_path, """
groups:
  - name: test
    prefix: /api
    routes:
      - path: /data
        method: get
        status: 200
        response: {}
""")
    route_map, _, _ = _load_config(config)
    assert ("GET", "/api/data") in route_map


def test_auth_config_loaded(tmp_path):
    config = write_config(tmp_path, """
groups:
  - name: test
    prefix: /api
    auth:
      type: basic
      username: admin
      password: pass
    routes:
      - path: /users
        method: GET
        status: 200
        response: {}
""")
    _, auth_map, prefixes = _load_config(config)
    assert "/api" in auth_map
    assert auth_map["/api"]["type"] == "basic"
    assert "/api" in prefixes


def test_public_group_not_in_auth_map(tmp_path):
    config = write_config(tmp_path, """
groups:
  - name: test
    prefix: /public
    routes:
      - path: /health
        method: GET
        status: 200
        response: {}
""")
    _, auth_map, _ = _load_config(config)
    assert "/public" not in auth_map


def test_invalid_yaml_exits(tmp_path):
    config = tmp_path / "mocks.yaml"
    config.write_text("groups: [invalid: yaml: {")
    with pytest.raises(SystemExit):
        _load_config(config)


def test_prefixes_sorted_longest_first(tmp_path):
    config = write_config(tmp_path, """
groups:
  - name: short
    prefix: /api
    auth:
      type: apikey
      header: X-Key
      key: k1
    routes:
      - path: /x
        method: GET
        status: 200
        response: {}
  - name: long
    prefix: /api/v2
    auth:
      type: apikey
      header: X-Key
      key: k2
    routes:
      - path: /x
        method: GET
        status: 200
        response: {}
""")
    _, _, prefixes = _load_config(config)
    assert prefixes.index("/api/v2") < prefixes.index("/api")
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: `ImportError: cannot import name '_load_config' from 'server'` (or `ModuleNotFoundError`).

- [ ] **Step 3: Implement _load_config in server.py**

Create `server.py`:

```python
import base64
import json
import sys
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def _load_config(
    config_path: Path,
) -> tuple[dict[tuple[str, str], tuple[int, object]], dict[str, dict], list[str]]:
    try:
        raw = yaml.safe_load(config_path.read_text())
    except Exception as e:
        sys.exit(f"Failed to load {config_path}: {e}")

    route_map: dict[tuple[str, str], tuple[int, object]] = {}
    auth_map: dict[str, dict] = {}
    all_prefixes: list[str] = []

    for group in raw.get("groups", []):
        prefix = group["prefix"].rstrip("/")
        all_prefixes.append(prefix)

        if "auth" in group:
            auth_map[prefix] = group["auth"]

        for route in group.get("routes", []):
            path = route["path"].rstrip("/")
            method = route["method"].upper()
            status = route["status"]
            full_path = f"{prefix}{path}".rstrip("/") or "/"

            has_inline = "response" in route
            has_file = "response_file" in route

            if has_inline and has_file:
                sys.exit(
                    f"Route {method} {full_path}: use 'response' or 'response_file', not both"
                )
            elif has_file:
                file_path = config_path.parent / route["response_file"]
                if not file_path.exists():
                    sys.exit(f"response_file not found: {file_path}")
                body = json.loads(file_path.read_text())
            elif has_inline:
                body = route["response"]
            else:
                sys.exit(
                    f"Route {method} {full_path}: must have 'response' or 'response_file'"
                )

            route_map[(method, full_path)] = (status, body)

    all_prefixes.sort(key=len, reverse=True)
    return route_map, auth_map, all_prefixes
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: All 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add server.py tests/test_config.py
git commit -m "feat: implement config loader with inline and file-based responses"
```

---

### Task 3: App factory, auth, and request handling

**Files:**
- Create: `tests/test_server.py`
- Modify: `server.py` — add `_check_auth`, `create_app`, module-level `app`

- [ ] **Step 1: Write the failing integration tests**

Create `tests/test_server.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `uv run pytest tests/test_server.py -v`
Expected: `ImportError: cannot import name 'create_app' from 'server'`.

- [ ] **Step 3: Add _check_auth and create_app to server.py**

Append to `server.py` (after `_load_config`):

```python
def _check_auth(auth_config: dict, request: Request) -> bool:
    if auth_config["type"] == "basic":
        header = request.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode()
            username, _, password = decoded.partition(":")
        except Exception:
            return False
        return username == auth_config["username"] and password == auth_config["password"]

    if auth_config["type"] == "apikey":
        return request.headers.get(auth_config["header"]) == auth_config["key"]

    return False


def create_app(config_path: Path) -> FastAPI:
    route_map, auth_map, prefixes = _load_config(config_path)

    app = FastAPI(title="Fake API Mocker")

    @app.api_route(
        "/{full_path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
    )
    async def catch_all(full_path: str, request: Request) -> JSONResponse:
        path = f"/{full_path}".rstrip("/") or "/"

        matched_prefix = next(
            (p for p in prefixes if path == p or path.startswith(p + "/")),
            None,
        )

        if matched_prefix is not None and matched_prefix in auth_map:
            auth_config = auth_map[matched_prefix]
            if not _check_auth(auth_config, request):
                headers = {}
                if auth_config["type"] == "basic":
                    headers["WWW-Authenticate"] = "Basic"
                return JSONResponse(
                    {"detail": "Unauthorized"}, status_code=401, headers=headers
                )

        method = request.method.upper()

        if (method, path) in route_map:
            status, body = route_map[(method, path)]
            return JSONResponse(body, status_code=status)

        for m, p in route_map:
            if p == path:
                return JSONResponse({"detail": "Method Not Allowed"}, status_code=405)

        return JSONResponse(
            {"detail": f"No mock configured for {method} {path}"},
            status_code=404,
        )

    return app
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `uv run pytest tests/test_server.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -v`
Expected: All tests in both files PASS.

- [ ] **Step 6: Commit**

```bash
git add server.py tests/test_server.py
git commit -m "feat: add FastAPI app factory with catch-all handler and auth"
```

---

### Task 4: Example config and responses

**Files:**
- Create: `mocks.yaml`
- Create: `responses/transactions.json`

This task creates the runtime config required for `app = create_app(Path("mocks.yaml"))` at module level (used when running the server directly), and serves as a working example for users.

- [ ] **Step 1: Create responses/transactions.json**

Run: `mkdir -p responses`

Create `responses/transactions.json`:

```json
[
  {"id": "tx_001", "amount": 1000, "currency": "USD", "status": "completed"},
  {"id": "tx_002", "amount": 2500, "currency": "USD", "status": "pending"},
  {"id": "tx_003", "amount": 750,  "currency": "EUR", "status": "completed"}
]
```

- [ ] **Step 2: Create mocks.yaml**

```yaml
groups:
  - name: payments-api
    prefix: /payments
    auth:
      type: basic
      username: alice
      password: secret123
    routes:
      - path: /charge
        method: POST
        status: 200
        response:
          id: "ch_123"
          status: "succeeded"
          amount: 5000
      - path: /charge/ch_123
        method: GET
        status: 200
        response:
          id: "ch_123"
          amount: 5000
          status: "succeeded"
      - path: /transactions
        method: GET
        status: 200
        response_file: responses/transactions.json

  - name: weather-api
    prefix: /weather
    auth:
      type: apikey
      header: X-API-Key
      key: my-secret-key
    routes:
      - path: /current
        method: GET
        status: 200
        response:
          temp: 72
          condition: sunny
          unit: fahrenheit

  - name: health
    prefix: /health
    routes:
      - path: /live
        method: GET
        status: 200
        response:
          status: ok
```

- [ ] **Step 3: Add module-level app to server.py**

Append to the bottom of `server.py`:

```python
app = create_app(Path("mocks.yaml"))
```

- [ ] **Step 4: Confirm the server starts without errors**

Run: `uv run uvicorn server:app --port 8000`
Expected: Server starts, no `SystemExit`. Press Ctrl+C to stop.

- [ ] **Step 5: Run full test suite one final time**

Run: `uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add mocks.yaml responses/transactions.json server.py
git commit -m "feat: add example mocks.yaml and wire module-level app"
```
