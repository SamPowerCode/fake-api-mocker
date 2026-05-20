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


def test_empty_yaml_exits(tmp_path):
    config = tmp_path / "mocks.yaml"
    config.write_text("")
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
