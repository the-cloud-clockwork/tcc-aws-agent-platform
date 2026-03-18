# P04 — Prompt Registry

## Objective

Build the Prompt Registry service: a Lambda API + DynamoDB + S3 backend for versioned prompt management. Supports push, get, list, diff, rollback, promote operations. Prompts are first-class versioned artifacts independent of agent code.

## Plane Tickets

ROOT-48

## Target Repo

`~/dev/tccw-prompt-registry`

## Dependencies

P01 (repo scaffold)

## Repo Structure

```
tccw-prompt-registry/
├── src/
│   └── prompt_registry/
│       ├── __init__.py
│       ├── handler.py         # Lambda handler (API Gateway integration)
│       ├── models.py          # Pydantic: PromptVersion, PromptMetadata
│       ├── storage.py         # S3 ops (read/write prompt text)
│       ├── registry.py        # DynamoDB ops (metadata CRUD)
│       └── resolver.py        # Version resolution logic
├── tests/
│   ├── conftest.py
│   ├── test_handler.py
│   ├── test_registry.py
│   ├── test_resolver.py
│   └── fixtures/
│       └── sample_prompts/
│           └── gap_detector/
│               ├── 1.0.0.txt
│               └── 1.2.0.txt
└── pyproject.toml
```

---

## Implementation Details

### Key Specs

- DynamoDB table: `qitp_prompt_registry` (PK=prompt_id, SK=version)
- S3 bucket: `qitp-prompt-registry` at key `{prompt_id}/{version}.txt`
- Status lifecycle: `draft` -> `stable` -> `deprecated`
- Only `stable` prompts resolve in paper/live mode
- `draft` prompts resolve in backtest/dev mode
- Version resolution: pinned (`gap_detector_v1.2`) or latest stable (`gap_detector`)
- Prompt ref format in blueprints: `prompt_ref: gap_detector_v1.2` or `prompt_ref: portfolio_recommender@2.0.0`

### Lambda API Endpoints (via API Gateway)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/prompts` | Push new version `{prompt_id, version, text, description}` |
| `GET` | `/prompts/{prompt_id}` | Get latest stable (or specific version via `?version=1.2.0`) |
| `GET` | `/prompts/{prompt_id}/versions` | List all versions with metadata |
| `POST` | `/prompts/{prompt_id}/promote` | Set version as stable `{version}` |
| `POST` | `/prompts/{prompt_id}/rollback` | Revert to previous stable `{version}` |
| `GET` | `/prompts/{prompt_id}/diff` | Diff two versions `?v1=1.0.0&v2=1.2.0` |

### DynamoDB Schema

```
PK: prompt_id (string)
SK: version (string, semver)
Attributes: description, status (draft|stable|deprecated), s3_key, created_at, updated_at, tags
```

### Resolver Logic

- Parse `gap_detector_v1.2` -> `(prompt_id="gap_detector", version="1.2")`
- Parse `portfolio_recommender@2.0.0` -> `(prompt_id="portfolio_recommender", version="2.0.0")`
- Parse `gap_detector` (no version) -> resolve latest stable
- In backtest mode: draft prompts are allowed. In paper/live: only stable.

---

## Full Source Code

### `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "prompt-registry"
version = "0.1.0"
description = "QITP Prompt Registry — versioned prompt management service"
requires-python = ">=3.11"
dependencies = [
    "boto3>=1.34",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "moto[dynamodb,s3]>=5.0",
    "pytest-cov>=5.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src/prompt_registry"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

### `src/prompt_registry/__init__.py`

```python
"""QITP Prompt Registry — versioned prompt management service."""

__version__ = "0.1.0"
```

### `src/prompt_registry/models.py`

```python
"""Pydantic models for prompt registry."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PromptStatus(str, Enum):
    DRAFT = "draft"
    STABLE = "stable"
    DEPRECATED = "deprecated"


class PromptVersion(BaseModel):
    """Stored metadata for a prompt version (maps to DynamoDB item)."""

    prompt_id: str
    version: str
    description: str = ""
    status: PromptStatus = PromptStatus.DRAFT
    s3_key: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    tags: list[str] = Field(default_factory=list)


class PromptCreateRequest(BaseModel):
    """Payload for POST /prompts."""

    prompt_id: str
    version: str
    text: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)


class PromptPromoteRequest(BaseModel):
    """Payload for POST /prompts/{prompt_id}/promote."""

    version: str


class PromptRollbackRequest(BaseModel):
    """Payload for POST /prompts/{prompt_id}/rollback."""

    version: str


class PromptResolveResponse(BaseModel):
    """Response when resolving a prompt ref."""

    prompt_id: str
    version: str
    text: str
    status: PromptStatus


class PromptVersionListItem(BaseModel):
    """Item in version list response."""

    prompt_id: str
    version: str
    description: str
    status: PromptStatus
    created_at: str
    tags: list[str] = Field(default_factory=list)


class Mode(str, Enum):
    """Execution mode that controls draft visibility."""

    BACKTEST = "backtest"
    DEV = "dev"
    PAPER = "paper"
    LIVE = "live"


# Modes where draft prompts are visible
DRAFT_ALLOWED_MODES: set[Mode] = {Mode.BACKTEST, Mode.DEV}
```

### `src/prompt_registry/storage.py`

```python
"""S3 operations for prompt text storage."""

from __future__ import annotations

import boto3
from botocore.exceptions import ClientError

DEFAULT_BUCKET = "qitp-prompt-registry"


class PromptStorage:
    """Read/write prompt text to S3."""

    def __init__(
        self,
        bucket: str = DEFAULT_BUCKET,
        s3_client=None,
    ) -> None:
        self.bucket = bucket
        self.s3 = s3_client or boto3.client("s3")

    def _key(self, prompt_id: str, version: str) -> str:
        return f"{prompt_id}/{version}.txt"

    def put(self, prompt_id: str, version: str, text: str) -> str:
        """Write prompt text to S3. Returns the S3 key."""
        key = self._key(prompt_id, version)
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=text.encode("utf-8"),
            ContentType="text/plain",
        )
        return key

    def get(self, prompt_id: str, version: str) -> str:
        """Read prompt text from S3."""
        key = self._key(prompt_id, version)
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].read().decode("utf-8")
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchKey":
                raise FileNotFoundError(
                    f"Prompt text not found: {prompt_id}/{version}"
                ) from exc
            raise

    def delete(self, prompt_id: str, version: str) -> None:
        """Delete prompt text from S3."""
        key = self._key(prompt_id, version)
        self.s3.delete_object(Bucket=self.bucket, Key=key)
```

### `src/prompt_registry/registry.py`

```python
"""DynamoDB operations for prompt metadata CRUD."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from prompt_registry.models import PromptStatus, PromptVersion

DEFAULT_TABLE = "qitp_prompt_registry"


class PromptRegistry:
    """DynamoDB-backed prompt metadata store."""

    def __init__(
        self,
        table_name: str = DEFAULT_TABLE,
        dynamodb_resource=None,
    ) -> None:
        self.table_name = table_name
        dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self.table = dynamodb.Table(table_name)

    def put_version(self, prompt: PromptVersion) -> None:
        """Write a prompt version record to DynamoDB."""
        self.table.put_item(Item=prompt.model_dump())

    def get_version(
        self, prompt_id: str, version: str
    ) -> Optional[PromptVersion]:
        """Get a specific prompt version."""
        resp = self.table.get_item(
            Key={"prompt_id": prompt_id, "version": version}
        )
        item = resp.get("Item")
        if not item:
            return None
        return PromptVersion(**item)

    def list_versions(self, prompt_id: str) -> list[PromptVersion]:
        """List all versions for a prompt_id, sorted by version."""
        resp = self.table.query(
            KeyConditionExpression=Key("prompt_id").eq(prompt_id)
        )
        items = resp.get("Items", [])
        versions = [PromptVersion(**item) for item in items]
        versions.sort(key=lambda v: _version_sort_key(v.version))
        return versions

    def get_latest_stable(self, prompt_id: str) -> Optional[PromptVersion]:
        """Get the latest stable version for a prompt_id."""
        versions = self.list_versions(prompt_id)
        stable = [v for v in versions if v.status == PromptStatus.STABLE]
        if not stable:
            return None
        return stable[-1]

    def get_latest_draft(self, prompt_id: str) -> Optional[PromptVersion]:
        """Get the latest draft version for a prompt_id."""
        versions = self.list_versions(prompt_id)
        drafts = [v for v in versions if v.status == PromptStatus.DRAFT]
        if not drafts:
            return None
        return drafts[-1]

    def update_status(
        self, prompt_id: str, version: str, new_status: PromptStatus
    ) -> Optional[PromptVersion]:
        """Update the status of a prompt version."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            resp = self.table.update_item(
                Key={"prompt_id": prompt_id, "version": version},
                UpdateExpression="SET #s = :status, updated_at = :now",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":status": new_status.value,
                    ":now": now,
                },
                ReturnValues="ALL_NEW",
                ConditionExpression="attribute_exists(prompt_id)",
            )
            return PromptVersion(**resp["Attributes"])
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise

    def promote(self, prompt_id: str, version: str) -> Optional[PromptVersion]:
        """
        Promote a version to stable.
        Deprecates the current stable version first.
        """
        # Deprecate current stable
        current_stable = self.get_latest_stable(prompt_id)
        if current_stable and current_stable.version != version:
            self.update_status(
                prompt_id,
                current_stable.version,
                PromptStatus.DEPRECATED,
            )

        return self.update_status(prompt_id, version, PromptStatus.STABLE)

    def rollback(self, prompt_id: str, version: str) -> Optional[PromptVersion]:
        """
        Rollback to a specific version.
        Deprecates the current stable and promotes the target version.
        """
        target = self.get_version(prompt_id, version)
        if not target:
            return None

        # Deprecate current stable
        current_stable = self.get_latest_stable(prompt_id)
        if current_stable and current_stable.version != version:
            self.update_status(
                prompt_id,
                current_stable.version,
                PromptStatus.DEPRECATED,
            )

        return self.update_status(prompt_id, version, PromptStatus.STABLE)


def _version_sort_key(version: str) -> tuple[int, ...]:
    """Convert semver string to tuple for sorting."""
    parts = []
    for part in version.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    # Pad to 3 components
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)
```

### `src/prompt_registry/resolver.py`

```python
"""Version resolution logic for prompt references."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from prompt_registry.models import (
    DRAFT_ALLOWED_MODES,
    Mode,
    PromptResolveResponse,
    PromptStatus,
)
from prompt_registry.registry import PromptRegistry
from prompt_registry.storage import PromptStorage


@dataclass
class ParsedRef:
    """Result of parsing a prompt reference string."""

    prompt_id: str
    version: Optional[str] = None


def parse_prompt_ref(ref: str) -> ParsedRef:
    """
    Parse a prompt reference into prompt_id and optional version.

    Supported formats:
        gap_detector            -> (prompt_id="gap_detector", version=None)
        gap_detector_v1.2       -> (prompt_id="gap_detector", version="1.2")
        gap_detector_v1.2.0     -> (prompt_id="gap_detector", version="1.2.0")
        portfolio_recommender@2.0.0 -> (prompt_id="portfolio_recommender", version="2.0.0")
    """
    # Format: name@version
    if "@" in ref:
        parts = ref.split("@", 1)
        return ParsedRef(prompt_id=parts[0], version=parts[1])

    # Format: name_vX.Y or name_vX.Y.Z
    match = re.match(r"^(.+?)_v(\d+(?:\.\d+)*)$", ref)
    if match:
        return ParsedRef(prompt_id=match.group(1), version=match.group(2))

    # No version specified — resolve to latest stable
    return ParsedRef(prompt_id=ref, version=None)


class PromptResolver:
    """Resolves prompt references to actual prompt text."""

    def __init__(
        self,
        registry: PromptRegistry,
        storage: PromptStorage,
    ) -> None:
        self.registry = registry
        self.storage = storage

    def resolve(
        self,
        ref: str,
        mode: Mode = Mode.LIVE,
    ) -> Optional[PromptResolveResponse]:
        """
        Resolve a prompt reference to its text content.

        In paper/live mode: only stable prompts are returned.
        In backtest/dev mode: draft prompts are also allowed.
        """
        parsed = parse_prompt_ref(ref)

        if parsed.version:
            return self._resolve_pinned(parsed, mode)
        return self._resolve_latest(parsed, mode)

    def _resolve_pinned(
        self, parsed: ParsedRef, mode: Mode
    ) -> Optional[PromptResolveResponse]:
        """Resolve a pinned version reference."""
        assert parsed.version is not None

        # Try exact match first
        prompt = self.registry.get_version(parsed.prompt_id, parsed.version)

        # If not found, try with .0 suffix (e.g., "1.2" -> "1.2.0")
        if prompt is None and parsed.version.count(".") < 2:
            padded = parsed.version + ".0" * (2 - parsed.version.count("."))
            prompt = self.registry.get_version(parsed.prompt_id, padded)

        if prompt is None:
            return None

        # Enforce mode-based access
        if prompt.status == PromptStatus.DRAFT and mode not in DRAFT_ALLOWED_MODES:
            return None

        if prompt.status == PromptStatus.DEPRECATED:
            return None

        text = self.storage.get(parsed.prompt_id, prompt.version)
        return PromptResolveResponse(
            prompt_id=prompt.prompt_id,
            version=prompt.version,
            text=text,
            status=prompt.status,
        )

    def _resolve_latest(
        self, parsed: ParsedRef, mode: Mode
    ) -> Optional[PromptResolveResponse]:
        """Resolve to the latest version based on mode."""
        # Always try stable first
        prompt = self.registry.get_latest_stable(parsed.prompt_id)

        # In draft-allowed modes, fall back to draft if no stable
        if prompt is None and mode in DRAFT_ALLOWED_MODES:
            prompt = self.registry.get_latest_draft(parsed.prompt_id)

        if prompt is None:
            return None

        text = self.storage.get(parsed.prompt_id, prompt.version)
        return PromptResolveResponse(
            prompt_id=prompt.prompt_id,
            version=prompt.version,
            text=text,
            status=prompt.status,
        )
```

### `src/prompt_registry/handler.py`

```python
"""Lambda handler for Prompt Registry API (API Gateway proxy integration)."""

from __future__ import annotations

import difflib
import json
import os
import re
import traceback
from typing import Any

import boto3

from prompt_registry.models import (
    Mode,
    PromptCreateRequest,
    PromptPromoteRequest,
    PromptResolveResponse,
    PromptRollbackRequest,
    PromptVersion,
    PromptVersionListItem,
)
from prompt_registry.registry import PromptRegistry
from prompt_registry.resolver import PromptResolver
from prompt_registry.storage import PromptStorage

# Configuration via environment
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "qitp_prompt_registry")
BUCKET_NAME = os.environ.get("S3_BUCKET", "qitp-prompt-registry")


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
    mode_str = _get_query_param(event, "mode") or "live"

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
```

### `tests/conftest.py`

```python
"""Shared test fixtures for prompt registry tests."""

from __future__ import annotations

import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from prompt_registry.registry import PromptRegistry
from prompt_registry.storage import PromptStorage

TEST_TABLE = "qitp_prompt_registry"
TEST_BUCKET = "qitp-prompt-registry"

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample_prompts"


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Set dummy AWS credentials for moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("DYNAMODB_TABLE", TEST_TABLE)
    monkeypatch.setenv("S3_BUCKET", TEST_BUCKET)


@pytest.fixture
def dynamodb_table():
    """Create a mocked DynamoDB table."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName=TEST_TABLE,
            KeySchema=[
                {"AttributeName": "prompt_id", "KeyType": "HASH"},
                {"AttributeName": "version", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "prompt_id", "AttributeType": "S"},
                {"AttributeName": "version", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.meta.client.get_waiter("table_exists").wait(
            TableName=TEST_TABLE
        )
        yield dynamodb


@pytest.fixture
def s3_bucket():
    """Create a mocked S3 bucket."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=TEST_BUCKET)
        yield s3


@pytest.fixture
def mock_aws_all():
    """Mock all AWS services together (for integration tests)."""
    with mock_aws():
        # DynamoDB
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName=TEST_TABLE,
            KeySchema=[
                {"AttributeName": "prompt_id", "KeyType": "HASH"},
                {"AttributeName": "version", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "prompt_id", "AttributeType": "S"},
                {"AttributeName": "version", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # S3
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=TEST_BUCKET)

        yield {
            "dynamodb": dynamodb,
            "s3": s3,
            "registry": PromptRegistry(
                table_name=TEST_TABLE, dynamodb_resource=dynamodb
            ),
            "storage": PromptStorage(
                bucket=TEST_BUCKET, s3_client=s3
            ),
        }


@pytest.fixture
def sample_prompt_text() -> dict[str, str]:
    """Load sample prompt texts from fixtures."""
    texts = {}
    for path in FIXTURES_DIR.rglob("*.txt"):
        key = f"{path.parent.name}/{path.stem}"
        texts[key] = path.read_text()
    return texts
```

### `tests/test_registry.py`

```python
"""Tests for DynamoDB registry operations."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from prompt_registry.models import PromptStatus, PromptVersion
from prompt_registry.registry import PromptRegistry

TABLE_NAME = "qitp_prompt_registry"


@pytest.fixture
def registry():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "prompt_id", "KeyType": "HASH"},
                {"AttributeName": "version", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "prompt_id", "AttributeType": "S"},
                {"AttributeName": "version", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield PromptRegistry(table_name=TABLE_NAME, dynamodb_resource=dynamodb)


def _make_prompt(prompt_id: str, version: str, status: str = "draft") -> PromptVersion:
    return PromptVersion(
        prompt_id=prompt_id,
        version=version,
        description=f"Test {version}",
        status=PromptStatus(status),
        s3_key=f"{prompt_id}/{version}.txt",
        tags=["test"],
    )


class TestRegistryPutGet:
    def test_put_and_get_version(self, registry):
        prompt = _make_prompt("gap_detector", "1.0.0")
        registry.put_version(prompt)

        result = registry.get_version("gap_detector", "1.0.0")
        assert result is not None
        assert result.prompt_id == "gap_detector"
        assert result.version == "1.0.0"
        assert result.status == PromptStatus.DRAFT

    def test_get_nonexistent_version(self, registry):
        result = registry.get_version("gap_detector", "99.0.0")
        assert result is None


class TestRegistryListVersions:
    def test_list_versions_sorted(self, registry):
        for ver in ["2.0.0", "1.0.0", "1.2.0"]:
            registry.put_version(_make_prompt("gap_detector", ver))

        versions = registry.list_versions("gap_detector")
        assert len(versions) == 3
        assert [v.version for v in versions] == ["1.0.0", "1.2.0", "2.0.0"]

    def test_list_versions_empty(self, registry):
        versions = registry.list_versions("nonexistent")
        assert versions == []


class TestRegistryLatestStable:
    def test_get_latest_stable(self, registry):
        v1 = _make_prompt("gap_detector", "1.0.0", "stable")
        v2 = _make_prompt("gap_detector", "1.2.0", "stable")
        v3 = _make_prompt("gap_detector", "2.0.0", "draft")
        for v in [v1, v2, v3]:
            registry.put_version(v)

        latest = registry.get_latest_stable("gap_detector")
        assert latest is not None
        assert latest.version == "1.2.0"

    def test_no_stable_returns_none(self, registry):
        registry.put_version(_make_prompt("gap_detector", "1.0.0", "draft"))
        assert registry.get_latest_stable("gap_detector") is None


class TestRegistryPromote:
    def test_promote_version(self, registry):
        registry.put_version(_make_prompt("gap_detector", "1.0.0", "stable"))
        registry.put_version(_make_prompt("gap_detector", "2.0.0", "draft"))

        result = registry.promote("gap_detector", "2.0.0")
        assert result is not None
        assert result.status == PromptStatus.STABLE

        # Old stable should be deprecated
        old = registry.get_version("gap_detector", "1.0.0")
        assert old.status == PromptStatus.DEPRECATED


class TestRegistryRollback:
    def test_rollback_to_previous(self, registry):
        registry.put_version(_make_prompt("gap_detector", "1.0.0", "deprecated"))
        registry.put_version(_make_prompt("gap_detector", "2.0.0", "stable"))

        result = registry.rollback("gap_detector", "1.0.0")
        assert result is not None
        assert result.status == PromptStatus.STABLE

        # Current stable should be deprecated
        old = registry.get_version("gap_detector", "2.0.0")
        assert old.status == PromptStatus.DEPRECATED

    def test_rollback_nonexistent(self, registry):
        result = registry.rollback("gap_detector", "99.0.0")
        assert result is None
```

### `tests/test_resolver.py`

```python
"""Tests for prompt reference resolution."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from prompt_registry.models import Mode, PromptStatus, PromptVersion
from prompt_registry.registry import PromptRegistry
from prompt_registry.resolver import PromptResolver, parse_prompt_ref
from prompt_registry.storage import PromptStorage

TABLE_NAME = "qitp_prompt_registry"
BUCKET_NAME = "qitp-prompt-registry"


class TestParsePromptRef:
    def test_plain_name(self):
        result = parse_prompt_ref("gap_detector")
        assert result.prompt_id == "gap_detector"
        assert result.version is None

    def test_underscore_v_format(self):
        result = parse_prompt_ref("gap_detector_v1.2")
        assert result.prompt_id == "gap_detector"
        assert result.version == "1.2"

    def test_underscore_v_format_full_semver(self):
        result = parse_prompt_ref("gap_detector_v1.2.0")
        assert result.prompt_id == "gap_detector"
        assert result.version == "1.2.0"

    def test_at_format(self):
        result = parse_prompt_ref("portfolio_recommender@2.0.0")
        assert result.prompt_id == "portfolio_recommender"
        assert result.version == "2.0.0"

    def test_complex_name_v_format(self):
        result = parse_prompt_ref("my_complex_prompt_v3.1")
        assert result.prompt_id == "my_complex_prompt"
        assert result.version == "3.1"


@pytest.fixture
def resolver_env():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "prompt_id", "KeyType": "HASH"},
                {"AttributeName": "version", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "prompt_id", "AttributeType": "S"},
                {"AttributeName": "version", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET_NAME)

        registry = PromptRegistry(table_name=TABLE_NAME, dynamodb_resource=dynamodb)
        storage = PromptStorage(bucket=BUCKET_NAME, s3_client=s3)
        resolver = PromptResolver(registry, storage)

        # Seed data
        for ver, status, text in [
            ("1.0.0", "stable", "You are gap detector v1."),
            ("1.2.0", "stable", "You are gap detector v1.2."),
            ("2.0.0", "draft", "You are gap detector v2 (draft)."),
        ]:
            storage.put("gap_detector", ver, text)
            registry.put_version(PromptVersion(
                prompt_id="gap_detector",
                version=ver,
                status=PromptStatus(status),
                s3_key=f"gap_detector/{ver}.txt",
            ))

        yield resolver


class TestResolverPinned:
    def test_resolve_at_format(self, resolver_env):
        result = resolver_env.resolve("gap_detector@1.0.0", mode=Mode.LIVE)
        assert result is not None
        assert result.version == "1.0.0"
        assert "v1." in result.text

    def test_resolve_v_format(self, resolver_env):
        result = resolver_env.resolve("gap_detector_v1.2.0", mode=Mode.LIVE)
        assert result is not None
        assert result.version == "1.2.0"

    def test_resolve_short_version_pads(self, resolver_env):
        """gap_detector_v1.2 should resolve to 1.2.0."""
        result = resolver_env.resolve("gap_detector_v1.2", mode=Mode.LIVE)
        assert result is not None
        assert result.version == "1.2.0"

    def test_draft_blocked_in_live_mode(self, resolver_env):
        result = resolver_env.resolve("gap_detector@2.0.0", mode=Mode.LIVE)
        assert result is None

    def test_draft_allowed_in_backtest_mode(self, resolver_env):
        result = resolver_env.resolve("gap_detector@2.0.0", mode=Mode.BACKTEST)
        assert result is not None
        assert result.status == PromptStatus.DRAFT

    def test_draft_allowed_in_dev_mode(self, resolver_env):
        result = resolver_env.resolve("gap_detector@2.0.0", mode=Mode.DEV)
        assert result is not None


class TestResolverLatest:
    def test_resolve_latest_stable(self, resolver_env):
        result = resolver_env.resolve("gap_detector", mode=Mode.LIVE)
        assert result is not None
        assert result.version == "1.2.0"
        assert result.status == PromptStatus.STABLE

    def test_resolve_nonexistent(self, resolver_env):
        result = resolver_env.resolve("nonexistent", mode=Mode.LIVE)
        assert result is None
```

### `tests/test_handler.py`

```python
"""Tests for Lambda handler / API Gateway integration."""

from __future__ import annotations

import json

import boto3
import pytest
from moto import mock_aws

from prompt_registry.handler import handler
from prompt_registry.models import PromptStatus, PromptVersion
from prompt_registry.registry import PromptRegistry
from prompt_registry.storage import PromptStorage

TABLE_NAME = "qitp_prompt_registry"
BUCKET_NAME = "qitp-prompt-registry"


def _api_event(
    method: str,
    path: str,
    body: dict | None = None,
    query: dict | None = None,
    path_params: dict | None = None,
) -> dict:
    """Build a minimal API Gateway proxy event."""
    event = {
        "httpMethod": method,
        "path": path,
        "headers": {"Content-Type": "application/json"},
        "queryStringParameters": query,
        "pathParameters": path_params,
        "body": json.dumps(body) if body else None,
    }
    return event


@pytest.fixture
def api_env(monkeypatch):
    """Set up mocked AWS services for handler tests."""
    with mock_aws():
        monkeypatch.setenv("DYNAMODB_TABLE", TABLE_NAME)
        monkeypatch.setenv("S3_BUCKET", BUCKET_NAME)

        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "prompt_id", "KeyType": "HASH"},
                {"AttributeName": "version", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "prompt_id", "AttributeType": "S"},
                {"AttributeName": "version", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET_NAME)

        # Reload handler module to pick up env vars
        import importlib
        import prompt_registry.handler as h
        h.TABLE_NAME = TABLE_NAME
        h.BUCKET_NAME = BUCKET_NAME

        yield


class TestCreatePrompt:
    def test_create_success(self, api_env):
        event = _api_event("POST", "/prompts", body={
            "prompt_id": "gap_detector",
            "version": "1.0.0",
            "text": "You are a gap detector.",
            "description": "Initial version",
            "tags": ["gap"],
        })
        resp = handler(event)
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["prompt_id"] == "gap_detector"
        assert body["status"] == "draft"

    def test_create_duplicate_fails(self, api_env):
        event = _api_event("POST", "/prompts", body={
            "prompt_id": "gap_detector",
            "version": "1.0.0",
            "text": "text",
        })
        handler(event)
        resp = handler(event)
        assert resp["statusCode"] == 409

    def test_create_invalid_body(self, api_env):
        event = _api_event("POST", "/prompts", body={"bad": "data"})
        resp = handler(event)
        assert resp["statusCode"] == 400


class TestGetPrompt:
    def test_get_latest_stable(self, api_env):
        # Create and promote
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "gap_detector", "version": "1.0.0",
            "text": "Version one.",
        }))
        handler(_api_event(
            "POST", "/prompts/gap_detector/promote",
            body={"version": "1.0.0"},
            path_params={"prompt_id": "gap_detector"},
        ))

        resp = handler(_api_event(
            "GET", "/prompts/gap_detector",
            path_params={"prompt_id": "gap_detector"},
        ))
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["version"] == "1.0.0"
        assert body["text"] == "Version one."

    def test_get_specific_version(self, api_env):
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "gap_detector", "version": "1.0.0",
            "text": "V1.",
        }))
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "gap_detector", "version": "2.0.0",
            "text": "V2.",
        }))
        # Promote 1.0.0
        handler(_api_event(
            "POST", "/prompts/gap_detector/promote",
            body={"version": "1.0.0"},
            path_params={"prompt_id": "gap_detector"},
        ))

        # Get specific draft in backtest mode
        resp = handler(_api_event(
            "GET", "/prompts/gap_detector",
            query={"version": "2.0.0", "mode": "backtest"},
            path_params={"prompt_id": "gap_detector"},
        ))
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["version"] == "2.0.0"
        assert body["text"] == "V2."

    def test_get_not_found(self, api_env):
        resp = handler(_api_event(
            "GET", "/prompts/nonexistent",
            path_params={"prompt_id": "nonexistent"},
        ))
        assert resp["statusCode"] == 404


class TestListVersions:
    def test_list_versions(self, api_env):
        for ver in ["1.0.0", "1.2.0", "2.0.0"]:
            handler(_api_event("POST", "/prompts", body={
                "prompt_id": "gap_detector", "version": ver,
                "text": f"Version {ver}.",
            }))

        resp = handler(_api_event(
            "GET", "/prompts/gap_detector/versions",
            path_params={"prompt_id": "gap_detector"},
        ))
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert len(body["versions"]) == 3


class TestPromote:
    def test_promote_success(self, api_env):
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "gap_detector", "version": "1.0.0", "text": "V1.",
        }))

        resp = handler(_api_event(
            "POST", "/prompts/gap_detector/promote",
            body={"version": "1.0.0"},
            path_params={"prompt_id": "gap_detector"},
        ))
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["status"] == "stable"

    def test_promote_nonexistent(self, api_env):
        resp = handler(_api_event(
            "POST", "/prompts/gap_detector/promote",
            body={"version": "99.0.0"},
            path_params={"prompt_id": "gap_detector"},
        ))
        assert resp["statusCode"] == 404


class TestRollback:
    def test_rollback_success(self, api_env):
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "gap_detector", "version": "1.0.0", "text": "V1.",
        }))
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "gap_detector", "version": "2.0.0", "text": "V2.",
        }))
        # Promote 1.0.0 then 2.0.0
        handler(_api_event(
            "POST", "/prompts/gap_detector/promote",
            body={"version": "1.0.0"},
            path_params={"prompt_id": "gap_detector"},
        ))
        handler(_api_event(
            "POST", "/prompts/gap_detector/promote",
            body={"version": "2.0.0"},
            path_params={"prompt_id": "gap_detector"},
        ))

        # Rollback to 1.0.0
        resp = handler(_api_event(
            "POST", "/prompts/gap_detector/rollback",
            body={"version": "1.0.0"},
            path_params={"prompt_id": "gap_detector"},
        ))
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["version"] == "1.0.0"
        assert body["status"] == "stable"


class TestDiff:
    def test_diff_two_versions(self, api_env):
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "gap_detector", "version": "1.0.0",
            "text": "Line 1\nLine 2\nLine 3\n",
        }))
        handler(_api_event("POST", "/prompts", body={
            "prompt_id": "gap_detector", "version": "1.2.0",
            "text": "Line 1\nLine 2 modified\nLine 3\nLine 4\n",
        }))

        resp = handler(_api_event(
            "GET", "/prompts/gap_detector/diff",
            query={"v1": "1.0.0", "v2": "1.2.0"},
            path_params={"prompt_id": "gap_detector"},
        ))
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert "Line 2 modified" in body["diff"]
        assert body["v1"] == "1.0.0"
        assert body["v2"] == "1.2.0"

    def test_diff_missing_params(self, api_env):
        resp = handler(_api_event(
            "GET", "/prompts/gap_detector/diff",
            query={"v1": "1.0.0"},
            path_params={"prompt_id": "gap_detector"},
        ))
        assert resp["statusCode"] == 400


class TestRouting:
    def test_unknown_route(self, api_env):
        resp = handler(_api_event("DELETE", "/prompts/whatever"))
        assert resp["statusCode"] == 404
```

### `tests/fixtures/sample_prompts/gap_detector/1.0.0.txt`

```text
You are a gap detection agent for investment portfolios.

Given the current portfolio holdings and the target allocation blueprint,
identify any gaps where:
- An asset class is missing from the portfolio
- An existing holding is significantly underweight vs target
- A new opportunity has emerged that fits the investment thesis

Output a structured list of gaps ranked by priority.
Each gap should include: asset_class, current_weight, target_weight, delta, recommendation.
```

### `tests/fixtures/sample_prompts/gap_detector/1.2.0.txt`

```text
You are a gap detection agent for investment portfolios (v1.2).

Given the current portfolio holdings and the target allocation blueprint,
identify any gaps where:
- An asset class is missing from the portfolio
- An existing holding is significantly underweight vs target (threshold: >2% delta)
- An existing holding is significantly overweight vs target (threshold: >3% delta)
- A new opportunity has emerged that fits the investment thesis
- A risk factor has changed requiring rebalancing

Output a structured JSON array of gaps ranked by priority.
Each gap object must include:
{
  "asset_class": "string",
  "current_weight": 0.0,
  "target_weight": 0.0,
  "delta": 0.0,
  "severity": "low|medium|high|critical",
  "recommendation": "string",
  "urgency_score": 0.0
}

Sort by urgency_score descending. Only include gaps with |delta| > 1%.
```

---

## Acceptance Criteria

- [ ] Lambda handler processes all 6 API endpoints correctly
- [ ] Version resolution handles pinned, @-tagged, and latest-stable formats
- [ ] Status lifecycle transitions work (draft -> stable -> deprecated)
- [ ] S3 read/write of prompt text works
- [ ] DynamoDB CRUD operations work
- [ ] Tests pass with mocked AWS services
- [ ] Draft-only-in-backtest rule enforced

## Test Plan

```bash
cd ~/dev/tccw-prompt-registry
pip install -e ".[dev]"
pytest -v
```

## Agent Instructions

This is a standalone service with no dependency on agent-core. Use boto3 for AWS services. Mock AWS in tests using moto. The handler should parse API Gateway proxy integration events. Include proper error handling and HTTP status codes.

Steps:
1. Scaffold the repo structure per the tree above
2. Write all source files exactly as specified in the inline code blocks
3. Write all test files exactly as specified
4. Write the fixture `.txt` files
5. Run `pip install -e ".[dev]"` and `pytest -v` to validate
6. Commit with a descriptive message
