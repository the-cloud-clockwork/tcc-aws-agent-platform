"""Lambda handler for Prompt Registry API (API Gateway proxy integration)."""

from __future__ import annotations

import difflib
import json
import os
import re
import traceback
from typing import Any

from prompt_registry.models import (
    Mode,
    PromptCreateRequest,
    PromptPromoteRequest,
    PromptRollbackRequest,
    PromptVersion,
    PromptVersionListItem,
)
from prompt_registry.registry import PromptRegistry
from prompt_registry.resolver import PromptResolver
from prompt_registry.storage import PromptStorage

# Configuration via environment
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "prompt_registry")
BUCKET_NAME = os.environ.get("S3_BUCKET", "prompt-registry")


def _get_registry() -> PromptRegistry:
    return PromptRegistry(table_name=TABLE_NAME)


def _get_storage() -> PromptStorage:
    return PromptStorage(bucket=BUCKET_NAME)


def _response(status_code: int, body: Any) -> dict:
    """Build an API Gateway proxy response."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }


def _parse_body(event: dict) -> dict:
    """Parse the JSON body from the API Gateway event."""
    body = event.get("body", "{}")
    if isinstance(body, str):
        return json.loads(body) if body else {}
    return body or {}


def _get_path_param(event: dict, name: str) -> str | None:
    """Extract a path parameter from the event."""
    params = event.get("pathParameters") or {}
    return params.get(name)


def _get_query_param(event: dict, name: str) -> str | None:
    """Extract a query string parameter from the event."""
    params = event.get("queryStringParameters") or {}
    return params.get(name)


# --- Route handlers ---


def handle_create_prompt(event: dict) -> dict:
    """POST /prompts — push a new prompt version."""
    body = _parse_body(event)
    try:
        req = PromptCreateRequest(**body)
    except Exception as exc:
        return _response(400, {"error": f"Invalid request: {exc}"})

    registry = _get_registry()
    storage = _get_storage()

    # Check if version already exists
    existing = registry.get_version(req.prompt_id, req.version)
    if existing:
        return _response(409, {"error": f"Version {req.version} already exists for {req.prompt_id}"})

    # Write text to S3
    s3_key = storage.put(req.prompt_id, req.version, req.text)

    # Write metadata to DynamoDB
    prompt = PromptVersion(
        prompt_id=req.prompt_id,
        version=req.version,
        description=req.description,
        s3_key=s3_key,
        tags=req.tags,
    )
    registry.put_version(prompt)

    return _response(201, {
        "message": "Prompt version created",
        "prompt_id": req.prompt_id,
        "version": req.version,
        "status": "draft",
    })


def handle_get_prompt(event: dict) -> dict:
    """GET /prompts/{prompt_id} — get prompt text (optionally pinned version)."""
    prompt_id = _get_path_param(event, "prompt_id")
    if not prompt_id:
        return _response(400, {"error": "prompt_id is required"})

    version = _get_query_param(event, "version")
    mode_str = _get_query_param(event, "mode") or "production"

    try:
        mode = Mode(mode_str)
    except ValueError:
        return _response(400, {"error": f"Invalid mode: {mode_str}"})

    registry = _get_registry()
    storage = _get_storage()
    resolver = PromptResolver(registry, storage)

    if version:
        ref = f"{prompt_id}@{version}"
    else:
        ref = prompt_id

    result = resolver.resolve(ref, mode=mode)
    if not result:
        return _response(404, {"error": f"Prompt not found: {prompt_id}"})

    return _response(200, result.model_dump())


def handle_list_versions(event: dict) -> dict:
    """GET /prompts/{prompt_id}/versions — list all versions."""
    prompt_id = _get_path_param(event, "prompt_id")
    if not prompt_id:
        return _response(400, {"error": "prompt_id is required"})

    registry = _get_registry()
    versions = registry.list_versions(prompt_id)

    items = [
        PromptVersionListItem(
            prompt_id=v.prompt_id,
            version=v.version,
            description=v.description,
            status=v.status,
            created_at=v.created_at,
            tags=v.tags,
        ).model_dump()
        for v in versions
    ]

    return _response(200, {"prompt_id": prompt_id, "versions": items})


def handle_promote(event: dict) -> dict:
    """POST /prompts/{prompt_id}/promote — promote a version to stable."""
    prompt_id = _get_path_param(event, "prompt_id")
    if not prompt_id:
        return _response(400, {"error": "prompt_id is required"})

    body = _parse_body(event)
    try:
        req = PromptPromoteRequest(**body)
    except Exception as exc:
        return _response(400, {"error": f"Invalid request: {exc}"})

    registry = _get_registry()

    # Check version exists
    existing = registry.get_version(prompt_id, req.version)
    if not existing:
        return _response(404, {"error": f"Version {req.version} not found"})

    result = registry.promote(prompt_id, req.version)
    if not result:
        return _response(500, {"error": "Failed to promote version"})

    return _response(200, {
        "message": f"Version {req.version} promoted to stable",
        "prompt_id": prompt_id,
        "version": req.version,
        "status": "stable",
    })


def handle_rollback(event: dict) -> dict:
    """POST /prompts/{prompt_id}/rollback — rollback to a previous version."""
    prompt_id = _get_path_param(event, "prompt_id")
    if not prompt_id:
        return _response(400, {"error": "prompt_id is required"})

    body = _parse_body(event)
    try:
        req = PromptRollbackRequest(**body)
    except Exception as exc:
        return _response(400, {"error": f"Invalid request: {exc}"})

    registry = _get_registry()

    result = registry.rollback(prompt_id, req.version)
    if not result:
        return _response(404, {"error": f"Version {req.version} not found"})

    return _response(200, {
        "message": f"Rolled back to version {req.version}",
        "prompt_id": prompt_id,
        "version": req.version,
        "status": "stable",
    })


def handle_diff(event: dict) -> dict:
    """GET /prompts/{prompt_id}/diff?v1=X&v2=Y — diff two versions."""
    prompt_id = _get_path_param(event, "prompt_id")
    if not prompt_id:
        return _response(400, {"error": "prompt_id is required"})

    v1 = _get_query_param(event, "v1")
    v2 = _get_query_param(event, "v2")
    if not v1 or not v2:
        return _response(400, {"error": "Both v1 and v2 query params required"})

    storage = _get_storage()

    try:
        text1 = storage.get(prompt_id, v1)
    except FileNotFoundError:
        return _response(404, {"error": f"Version {v1} text not found"})

    try:
        text2 = storage.get(prompt_id, v2)
    except FileNotFoundError:
        return _response(404, {"error": f"Version {v2} text not found"})

    diff_lines = list(difflib.unified_diff(
        text1.splitlines(keepends=True),
        text2.splitlines(keepends=True),
        fromfile=f"{prompt_id}/{v1}",
        tofile=f"{prompt_id}/{v2}",
    ))

    return _response(200, {
        "prompt_id": prompt_id,
        "v1": v1,
        "v2": v2,
        "diff": "".join(diff_lines),
    })


# --- Router ---

# Route patterns: (method, path_regex) -> handler
ROUTES: list[tuple[str, str, callable]] = [
    ("POST", r"^/prompts$", handle_create_prompt),
    ("GET", r"^/prompts/(?P<prompt_id>[^/]+)/versions$", handle_list_versions),
    ("GET", r"^/prompts/(?P<prompt_id>[^/]+)/diff$", handle_diff),
    ("POST", r"^/prompts/(?P<prompt_id>[^/]+)/promote$", handle_promote),
    ("POST", r"^/prompts/(?P<prompt_id>[^/]+)/rollback$", handle_rollback),
    ("GET", r"^/prompts/(?P<prompt_id>[^/]+)$", handle_get_prompt),
]


def handler(event: dict, context: Any = None) -> dict:
    """
    Lambda entry point — routes API Gateway proxy events to handlers.
    """
    method = event.get("httpMethod", "GET")
    path = event.get("path", "/")

    for route_method, pattern, route_handler in ROUTES:
        if method != route_method:
            continue
        match = re.match(pattern, path)
        if match:
            # Inject matched path params into the event
            if match.groupdict():
                event.setdefault("pathParameters", {})
                event["pathParameters"].update(match.groupdict())
            try:
                return route_handler(event)
            except Exception as exc:
                traceback.print_exc()
                return _response(500, {"error": str(exc)})

    return _response(404, {"error": f"Route not found: {method} {path}"})
