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
