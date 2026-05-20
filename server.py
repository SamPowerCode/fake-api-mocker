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
