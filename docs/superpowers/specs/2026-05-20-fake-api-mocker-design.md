# Fake API Mocker — Design Spec

**Date:** 2026-05-20
**Status:** Approved

## Overview

A local mock API server built with FastAPI that returns predetermined JSON responses defined in a static YAML config file. Intended for local development and testing — stub out external APIs without hitting real services.

## Architecture

Single-file FastAPI server (`server.py`) with a catch-all route handler. At startup, the server loads `mocks.yaml`, builds two in-memory structures:

- A lookup dict: `{(METHOD, full_path) → (status_code, response_body)}`
- An auth map: `{prefix → auth_config}`

Every incoming request is handled by one route (`ANY /{full_path:path}`), which:
1. Finds the matching group by longest-prefix match (e.g., `/api/v1` beats `/api` for a request to `/api/v1/users`)
2. Validates auth for that group
3. Looks up the method + path in the dict (methods normalized to uppercase)
4. Returns the configured status code and JSON response body

## Config File Structure

Single `mocks.yaml` file. Route groups are defined under a top-level `groups` key. Each group has:

- `name` — human-readable identifier
- `prefix` — URL prefix for all routes in this group
- `auth` — auth config (see Auth section)
- `routes` — list of route definitions

Each route has:
- `path` — path relative to the group prefix
- `method` — HTTP method (GET, POST, PUT, DELETE, etc.)
- `status` — HTTP status code to return
- `response` — any valid JSON value (object, array, string, number) defined inline *(mutually exclusive with `response_file`)*
- `response_file` — path to a `.json` file (relative to `mocks.yaml`) whose contents are returned as the response body. Use this for large payloads that would be unwieldy inline.

Exactly one of `response` or `response_file` must be present on each route. If the referenced file is missing, the server exits with a clear error at startup.

Example:

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
      - path: /transactions
        method: GET
        status: 200
        response_file: responses/transactions.json  # large payload in separate file

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
          condition: "sunny"
```

## Auth

Two supported auth types, configured per group:

**Basic Auth** (`type: basic`):
- Client sends `Authorization: Basic <base64(username:password)>` header
- Server validates against configured `username` and `password`
- Wrong/missing credentials → `401` with `WWW-Authenticate: Basic` header

**API Key** (`type: apikey`):
- Client sends the configured header (e.g., `X-API-Key`) with the configured key value
- Server validates the header value
- Wrong/missing credentials → `401`

Groups with no `auth` key are public (no auth required).

## Error Handling

| Scenario | Response |
|---|---|
| No matching route | `404 {"detail": "No mock configured for {METHOD} {path}"}` |
| Path matched, wrong method | `405 Method Not Allowed` |
| Missing or wrong credentials | `401 {"detail": "Unauthorized"}` |
| Invalid YAML on startup | Server exits with a clear error message |
| `response_file` not found at startup | Server exits with a clear error message |
| Neither `response` nor `response_file` on a route | Server exits with a clear error message |

Trailing slashes are normalized on load — `/foo` and `/foo/` are treated as the same route. Duplicate routes: last definition in the file wins.

## Project Structure

```
fake-api-mocker/
├── server.py           # all server logic
├── mocks.yaml          # mock definitions (user-edited)
├── responses/          # optional directory for large JSON response files
│   └── *.json
├── pyproject.toml
└── uv.lock
```

## Running

```bash
uv run uvicorn server:app --reload --port 8000
```

Auto-generated API docs available at `http://localhost:8000/docs`.

## Dependencies

Managed via `uv` with `pyproject.toml`:

- `fastapi`
- `uvicorn`
- `pyyaml`
