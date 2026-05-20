# fake-api-mocker

A local mock API server that returns predetermined JSON responses from a static YAML config. Useful for stubbing out external APIs during development and testing.

## Setup

```bash
uv sync
```

## Running

```bash
uv run uvicorn server:app --reload --port 8000
```

Interactive docs at `http://localhost:8000/docs`.

## Configuration

Edit `mocks.yaml` to define your mock APIs. The file defines route groups — each group has a URL prefix, optional auth, and a list of routes.

```yaml
groups:
  - name: my-api
    prefix: /api
    auth:
      type: basic
      username: alice
      password: secret123
    routes:
      - path: /users
        method: GET
        status: 200
        response:
          - id: 1
            name: alice
          - id: 2
            name: bob

      - path: /users/1
        method: GET
        status: 200
        response:
          id: 1
          name: alice

      - path: /bulk-data
        method: GET
        status: 200
        response_file: responses/bulk-data.json  # path relative to mocks.yaml
```

### Auth types

**Basic Auth**
```yaml
auth:
  type: basic
  username: alice
  password: secret123
```
Clients send `Authorization: Basic <base64(username:password)>`.

**API Key**
```yaml
auth:
  type: apikey
  header: X-API-Key
  key: my-secret-key
```
Clients send the configured header with the configured key value.

**No auth** — omit the `auth` key entirely.

### Large responses

Use `response_file` instead of `response` to load the body from a JSON file. The path is relative to `mocks.yaml`.

```yaml
- path: /transactions
  method: GET
  status: 200
  response_file: responses/transactions.json
```

### Error responses

Return any status code:

```yaml
- path: /not-found
  method: GET
  status: 404
  response:
    error: resource not found
```

## Behavior

| Scenario | Response |
|---|---|
| Matching route, valid auth | Configured status + JSON body |
| Missing or wrong credentials | `401 Unauthorized` |
| Path exists, wrong method | `405 Method Not Allowed` |
| No matching route | `404 {"detail": "No mock configured for ..."}` |
| Config error at startup | Server exits with a clear error message |

Trailing slashes on request paths are normalized. Duplicate routes or prefixes in `mocks.yaml` cause a startup error.

## Running tests

```bash
uv run pytest -v
```
