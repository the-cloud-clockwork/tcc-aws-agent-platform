# P06 — Artifacts MCP Server

## Objective
Build artifacts-mcp: universal output pipeline for all QITP agents. Every artifact (charts, reports, backtest results, recommendations) flows through this MCP to S3 storage with DynamoDB catalog and signed URL generation.

## Plane Tickets
ROOT-53

## Target Repo
`~/dev/tccw-mcp-artifacts`

## Dependencies
P02 (core schemas)

## Repo Structure
```
tccw-mcp-artifacts/
├── src/
│   └── mcp_artifacts/
│       ├── __init__.py
│       ├── server.py           # MCP server entrypoint
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── create.py       # create_artifact tool
│       │   ├── get.py          # get_artifact tool
│       │   ├── poll.py         # poll_artifact tool
│       │   └── list_artifacts.py  # list_artifacts tool
│       ├── storage.py          # S3 operations
│       ├── catalog.py          # DynamoDB catalog operations
│       └── schemas.py          # ArtifactType, ArtifactMeta, CreateResult, ArtifactResult
├── tests/
│   ├── conftest.py
│   ├── test_create.py
│   ├── test_get.py
│   └── test_catalog.py
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## Full Inline Code

### `pyproject.toml`
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mcp-artifacts"
version = "0.1.0"
description = "QITP Artifacts MCP Server — universal output pipeline for all agents"
requires-python = ">=3.11"
dependencies = [
    "mcp[server]>=1.0.0",
    "boto3>=1.34.0",
    "pydantic>=2.0.0",
    "uvicorn>=0.27.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "moto[s3,dynamodb]>=5.0.0",
]

[project.scripts]
mcp-artifacts = "mcp_artifacts.server:main"

[tool.hatch.build.targets.wheel]
packages = ["src/mcp_artifacts"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### `src/mcp_artifacts/__init__.py`
```python
"""QITP Artifacts MCP Server — universal output pipeline for all agents."""

__version__ = "0.1.0"
```

### `src/mcp_artifacts/schemas.py`
```python
"""Artifact schemas used across the MCP server."""

from __future__ import annotations

import base64
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    """Supported artifact types."""

    CHART = "chart"
    REPORT = "report"
    BACKTEST_RESULT = "backtest_result"
    RECOMMENDATION = "recommendation"
    IMAGE = "image"
    DATA_EXPORT = "data_export"


# Map artifact type to file extension and content-type
ARTIFACT_TYPE_MAP: dict[ArtifactType, tuple[str, str]] = {
    ArtifactType.CHART: (".jsx", "text/jsx"),
    ArtifactType.REPORT: (".md", "text/markdown"),
    ArtifactType.BACKTEST_RESULT: (".json", "application/json"),
    ArtifactType.RECOMMENDATION: (".json", "application/json"),
    ArtifactType.IMAGE: (".png", "image/png"),
    ArtifactType.DATA_EXPORT: (".csv", "text/csv"),
}


class ArtifactMeta(BaseModel):
    """Metadata stored in DynamoDB for each artifact."""

    artifact_id: str = Field(description="UUID identifier")
    type: ArtifactType
    status: Literal["processing", "ready", "error"] = "processing"
    s3_key: str
    signed_url: str | None = None
    agent_id: str | None = None
    execution_id: str | None = None
    created_at: datetime
    expires_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class CreateResult(BaseModel):
    """Returned immediately after create_artifact."""

    artifact_id: str
    status: str
    s3_key: str


class ArtifactResult(BaseModel):
    """Returned by get_artifact and poll_artifact."""

    artifact_id: str
    status: str
    signed_url: str | None = None
    type: ArtifactType | None = None
    metadata: dict = Field(default_factory=dict)


def encode_content(artifact_type: ArtifactType, content: str) -> bytes:
    """Convert content string to bytes based on artifact type.

    For IMAGE type, content is base64-encoded and decoded to raw bytes.
    For all other types, content is UTF-8 encoded.
    """
    if artifact_type == ArtifactType.IMAGE:
        return base64.b64decode(content)
    return content.encode("utf-8")


def filename_for_type(artifact_type: ArtifactType) -> str:
    """Return the default filename for a given artifact type."""
    ext, _ = ARTIFACT_TYPE_MAP[artifact_type]
    return f"artifact{ext}"


def content_type_for_type(artifact_type: ArtifactType) -> str:
    """Return the S3 content-type for a given artifact type."""
    _, ct = ARTIFACT_TYPE_MAP[artifact_type]
    return ct
```

### `src/mcp_artifacts/storage.py`
```python
"""S3 storage operations for artifacts."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

logger = logging.getLogger(__name__)

BUCKET_NAME = "qitp-artifacts"
SIGNED_URL_EXPIRY = 3600  # 1 hour


class ArtifactStorage:
    """Handles S3 put/get and signed URL generation."""

    def __init__(self, s3_client: "S3Client | None" = None, bucket: str = BUCKET_NAME) -> None:
        self._s3: "S3Client" = s3_client or boto3.client("s3")
        self._bucket = bucket

    def put_object(self, s3_key: str, body: bytes, content_type: str) -> None:
        """Upload bytes to S3."""
        self._s3.put_object(
            Bucket=self._bucket,
            Key=s3_key,
            Body=body,
            ContentType=content_type,
        )
        logger.info("Uploaded s3://%s/%s (%d bytes)", self._bucket, s3_key, len(body))

    def generate_signed_url(self, s3_key: str, expiry: int = SIGNED_URL_EXPIRY) -> str:
        """Generate a pre-signed GET URL for the given key."""
        url: str = self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": s3_key},
            ExpiresIn=expiry,
        )
        return url

    def head_object(self, s3_key: str) -> bool:
        """Check whether an object exists in S3."""
        try:
            self._s3.head_object(Bucket=self._bucket, Key=s3_key)
            return True
        except self._s3.exceptions.ClientError:
            return False
```

### `src/mcp_artifacts/catalog.py`
```python
"""DynamoDB catalog operations for artifact metadata."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import boto3
from boto3.dynamodb.conditions import Attr, Key

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

TABLE_NAME = "qitp_artifacts"


class ArtifactCatalog:
    """DynamoDB CRUD for the artifact catalog table."""

    def __init__(self, dynamodb_resource=None, table_name: str = TABLE_NAME) -> None:
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")
        self._table_name = table_name
        self._table = self._dynamodb.Table(table_name)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_entry(
        self,
        artifact_id: str,
        artifact_type: str,
        s3_key: str,
        agent_id: str | None = None,
        execution_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Insert a new catalog entry with status=processing."""
        now = datetime.now(timezone.utc).isoformat()
        item: dict[str, Any] = {
            "artifact_id": artifact_id,
            "type": artifact_type,
            "status": "processing",
            "s3_key": s3_key,
            "created_at": now,
            "metadata": json.dumps(metadata or {}),
        }
        if agent_id:
            item["agent_id"] = agent_id
        if execution_id:
            item["execution_id"] = execution_id

        self._table.put_item(Item=item)
        logger.info("Created catalog entry %s (type=%s)", artifact_id, artifact_type)
        return item

    def update_status(self, artifact_id: str, status: str) -> None:
        """Update the status field of an artifact."""
        self._table.update_item(
            Key={"artifact_id": artifact_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": status},
        )
        logger.info("Updated %s status to %s", artifact_id, status)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_entry(self, artifact_id: str) -> dict[str, Any] | None:
        """Fetch a single catalog entry by artifact_id (PK)."""
        resp = self._table.get_item(Key={"artifact_id": artifact_id})
        item = resp.get("Item")
        if item and "metadata" in item and isinstance(item["metadata"], str):
            item["metadata"] = json.loads(item["metadata"])
        return item

    def list_entries(
        self,
        artifact_type: str | None = None,
        agent_id: str | None = None,
        date: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query/scan the catalog with optional filters.

        Filters:
        - artifact_type: use GSI1 (type-created_at-index)
        - agent_id: use GSI2 (agent_id-created_at-index)
        - date: filter created_at begins_with date string (YYYY-MM-DD)
        - If no type/agent_id provided, falls back to table scan with filters.
        """
        if artifact_type:
            kwargs: dict[str, Any] = {
                "IndexName": "type-created_at-index",
                "KeyConditionExpression": Key("type").eq(artifact_type),
                "Limit": limit,
                "ScanIndexForward": False,
            }
            if date:
                kwargs["KeyConditionExpression"] &= Key("created_at").begins_with(date)
            if agent_id:
                kwargs["FilterExpression"] = Attr("agent_id").eq(agent_id)
            resp = self._table.query(**kwargs)

        elif agent_id:
            kwargs = {
                "IndexName": "agent_id-created_at-index",
                "KeyConditionExpression": Key("agent_id").eq(agent_id),
                "Limit": limit,
                "ScanIndexForward": False,
            }
            if date:
                kwargs["KeyConditionExpression"] &= Key("created_at").begins_with(date)
            resp = self._table.query(**kwargs)

        else:
            scan_kwargs: dict[str, Any] = {"Limit": limit}
            filters = []
            if date:
                filters.append(Attr("created_at").begins_with(date))
            if filters:
                combined = filters[0]
                for f in filters[1:]:
                    combined &= f
                scan_kwargs["FilterExpression"] = combined
            resp = self._table.scan(**scan_kwargs)

        items = resp.get("Items", [])
        for item in items:
            if "metadata" in item and isinstance(item["metadata"], str):
                item["metadata"] = json.loads(item["metadata"])
        return items

    # ------------------------------------------------------------------
    # Table bootstrap (for tests / local dev)
    # ------------------------------------------------------------------

    @classmethod
    def ensure_table(cls, dynamodb_resource=None, table_name: str = TABLE_NAME):
        """Create the DynamoDB table if it does not exist. Used in tests."""
        ddb = dynamodb_resource or boto3.resource("dynamodb")
        try:
            table = ddb.Table(table_name)
            table.load()
            return table
        except Exception:
            pass

        table = ddb.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "artifact_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "artifact_id", "AttributeType": "S"},
                {"AttributeName": "type", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
                {"AttributeName": "agent_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "type-created_at-index",
                    "KeySchema": [
                        {"AttributeName": "type", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "agent_id-created_at-index",
                    "KeySchema": [
                        {"AttributeName": "agent_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        return table
```

### `src/mcp_artifacts/tools/__init__.py`
```python
"""Artifact MCP tools."""
```

### `src/mcp_artifacts/tools/create.py`
```python
"""create_artifact tool implementation."""

from __future__ import annotations

import uuid
from typing import Any

from mcp_artifacts.catalog import ArtifactCatalog
from mcp_artifacts.schemas import (
    ArtifactType,
    CreateResult,
    content_type_for_type,
    encode_content,
    filename_for_type,
)
from mcp_artifacts.storage import ArtifactStorage


async def create_artifact(
    type: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    agent_id: str | None = None,
    execution_id: str | None = None,
    storage: ArtifactStorage | None = None,
    catalog: ArtifactCatalog | None = None,
) -> dict[str, Any]:
    """Create a new artifact: store to S3 and register in DynamoDB.

    Parameters
    ----------
    type:
        One of the ArtifactType enum values.
    content:
        Raw content string. For IMAGE type this must be base64-encoded.
    metadata:
        Arbitrary key/value metadata dict.
    agent_id:
        Optional agent identifier that created this artifact.
    execution_id:
        Optional execution/run identifier.
    storage:
        Injected ArtifactStorage (for testing).
    catalog:
        Injected ArtifactCatalog (for testing).

    Returns
    -------
    dict with artifact_id, status, s3_key.
    """
    _storage = storage or ArtifactStorage()
    _catalog = catalog or ArtifactCatalog()

    artifact_type = ArtifactType(type)
    artifact_id = str(uuid.uuid4())
    filename = filename_for_type(artifact_type)
    s3_key = f"{artifact_id}/{filename}"

    # 1. Create catalog entry (status=processing)
    _catalog.create_entry(
        artifact_id=artifact_id,
        artifact_type=artifact_type.value,
        s3_key=s3_key,
        agent_id=agent_id,
        execution_id=execution_id,
        metadata=metadata,
    )

    try:
        # 2. Upload content to S3
        body = encode_content(artifact_type, content)
        ct = content_type_for_type(artifact_type)
        _storage.put_object(s3_key, body, ct)

        # 3. Update status to ready
        _catalog.update_status(artifact_id, "ready")
    except Exception:
        _catalog.update_status(artifact_id, "error")
        raise

    result = CreateResult(artifact_id=artifact_id, status="ready", s3_key=s3_key)
    return result.model_dump()
```

### `src/mcp_artifacts/tools/get.py`
```python
"""get_artifact tool implementation."""

from __future__ import annotations

from typing import Any

from mcp_artifacts.catalog import ArtifactCatalog
from mcp_artifacts.schemas import ArtifactResult, ArtifactType
from mcp_artifacts.storage import ArtifactStorage


async def get_artifact(
    artifact_id: str,
    storage: ArtifactStorage | None = None,
    catalog: ArtifactCatalog | None = None,
) -> dict[str, Any]:
    """Retrieve artifact metadata and signed URL if ready.

    Parameters
    ----------
    artifact_id:
        The UUID of the artifact to retrieve.

    Returns
    -------
    dict with artifact_id, status, signed_url (if ready), type, metadata.
    """
    _storage = storage or ArtifactStorage()
    _catalog = catalog or ArtifactCatalog()

    entry = _catalog.get_entry(artifact_id)
    if entry is None:
        return ArtifactResult(
            artifact_id=artifact_id,
            status="not_found",
        ).model_dump()

    signed_url = None
    if entry["status"] == "ready":
        signed_url = _storage.generate_signed_url(entry["s3_key"])

    artifact_type = ArtifactType(entry["type"]) if "type" in entry else None
    meta = entry.get("metadata", {})

    return ArtifactResult(
        artifact_id=artifact_id,
        status=entry["status"],
        signed_url=signed_url,
        type=artifact_type,
        metadata=meta,
    ).model_dump()
```

### `src/mcp_artifacts/tools/poll.py`
```python
"""poll_artifact tool implementation."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp_artifacts.catalog import ArtifactCatalog
from mcp_artifacts.schemas import ArtifactResult, ArtifactType
from mcp_artifacts.storage import ArtifactStorage


async def poll_artifact(
    artifact_id: str,
    timeout_s: int = 60,
    storage: ArtifactStorage | None = None,
    catalog: ArtifactCatalog | None = None,
) -> dict[str, Any]:
    """Poll DynamoDB every 2s until the artifact is ready or timeout.

    Parameters
    ----------
    artifact_id:
        The UUID of the artifact to poll.
    timeout_s:
        Maximum seconds to wait (default 60).

    Returns
    -------
    dict with artifact_id, status, signed_url (if ready), type, metadata.
    """
    _storage = storage or ArtifactStorage()
    _catalog = catalog or ArtifactCatalog()

    elapsed = 0.0
    poll_interval = 2.0

    while elapsed < timeout_s:
        entry = _catalog.get_entry(artifact_id)

        if entry is None:
            return ArtifactResult(
                artifact_id=artifact_id,
                status="not_found",
            ).model_dump()

        if entry["status"] in ("ready", "error"):
            signed_url = None
            if entry["status"] == "ready":
                signed_url = _storage.generate_signed_url(entry["s3_key"])

            artifact_type = ArtifactType(entry["type"]) if "type" in entry else None
            meta = entry.get("metadata", {})

            return ArtifactResult(
                artifact_id=artifact_id,
                status=entry["status"],
                signed_url=signed_url,
                type=artifact_type,
                metadata=meta,
            ).model_dump()

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    # Timeout reached
    return ArtifactResult(
        artifact_id=artifact_id,
        status="timeout",
    ).model_dump()
```

### `src/mcp_artifacts/tools/list_artifacts.py`
```python
"""list_artifacts tool implementation."""

from __future__ import annotations

from typing import Any

from mcp_artifacts.catalog import ArtifactCatalog
from mcp_artifacts.schemas import ArtifactMeta, ArtifactType


async def list_artifacts(
    type: str | None = None,
    agent_id: str | None = None,
    date: str | None = None,
    limit: int = 50,
    catalog: ArtifactCatalog | None = None,
) -> list[dict[str, Any]]:
    """List artifacts with optional filters. Returns metadata only, no URLs.

    Parameters
    ----------
    type:
        Filter by ArtifactType value (e.g. "chart", "report").
    agent_id:
        Filter by the agent that created the artifact.
    date:
        Filter by date prefix (YYYY-MM-DD).
    limit:
        Max results to return (default 50).

    Returns
    -------
    list of ArtifactMeta dicts (no signed_url).
    """
    _catalog = catalog or ArtifactCatalog()

    entries = _catalog.list_entries(
        artifact_type=type,
        agent_id=agent_id,
        date=date,
        limit=limit,
    )

    results: list[dict[str, Any]] = []
    for entry in entries:
        meta = ArtifactMeta(
            artifact_id=entry["artifact_id"],
            type=ArtifactType(entry["type"]),
            status=entry["status"],
            s3_key=entry["s3_key"],
            signed_url=None,
            agent_id=entry.get("agent_id"),
            execution_id=entry.get("execution_id"),
            created_at=entry["created_at"],
            expires_at=None,
            metadata=entry.get("metadata", {}),
        )
        results.append(meta.model_dump())

    return results
```

### `src/mcp_artifacts/server.py`
```python
"""MCP server entrypoint for QITP Artifacts."""

from __future__ import annotations

import json
import logging

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from mcp_artifacts.tools.create import create_artifact
from mcp_artifacts.tools.get import get_artifact
from mcp_artifacts.tools.list_artifacts import list_artifacts
from mcp_artifacts.tools.poll import poll_artifact

logger = logging.getLogger(__name__)

app = Server("mcp-artifacts")


# ------------------------------------------------------------------
# Tool definitions
# ------------------------------------------------------------------

TOOLS = [
    Tool(
        name="create_artifact",
        description=(
            "Store an artifact (chart, report, backtest result, recommendation, image, "
            "data export) to S3 and register it in the artifact catalog. Returns the "
            "artifact_id and S3 key immediately."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["chart", "report", "backtest_result", "recommendation", "image", "data_export"],
                    "description": "Artifact type",
                },
                "content": {
                    "type": "string",
                    "description": "Raw content. Base64 for image type, plain text for others.",
                },
                "metadata": {
                    "type": "object",
                    "description": "Arbitrary key/value metadata",
                    "default": {},
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent that produced this artifact",
                },
                "execution_id": {
                    "type": "string",
                    "description": "Execution or run identifier",
                },
            },
            "required": ["type", "content"],
        },
    ),
    Tool(
        name="get_artifact",
        description=(
            "Retrieve artifact metadata and a signed URL (if ready). "
            "Returns current status if the artifact is still processing."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "artifact_id": {
                    "type": "string",
                    "description": "UUID of the artifact",
                },
            },
            "required": ["artifact_id"],
        },
    ),
    Tool(
        name="poll_artifact",
        description=(
            "Poll until the artifact is ready (or timeout). Returns signed URL when ready."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "artifact_id": {
                    "type": "string",
                    "description": "UUID of the artifact",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "Max seconds to wait (default 60)",
                    "default": 60,
                },
            },
            "required": ["artifact_id"],
        },
    ),
    Tool(
        name="list_artifacts",
        description=(
            "List artifacts with optional filters. Returns metadata only (no URLs)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["chart", "report", "backtest_result", "recommendation", "image", "data_export"],
                    "description": "Filter by artifact type",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Filter by agent ID",
                },
                "date": {
                    "type": "string",
                    "description": "Filter by date (YYYY-MM-DD)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 50)",
                    "default": 50,
                },
            },
        },
    ),
]


@app.list_tools()
async def handle_list_tools() -> list[Tool]:
    """Return all available artifact tools."""
    return TOOLS


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch tool calls to the appropriate handler."""
    handlers = {
        "create_artifact": create_artifact,
        "get_artifact": get_artifact,
        "poll_artifact": poll_artifact,
        "list_artifacts": list_artifacts,
    }

    handler = handlers.get(name)
    if handler is None:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    try:
        result = await handler(**arguments)
        return [TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


# ------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------

def main() -> None:
    """Run the MCP server over stdio."""
    import asyncio

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    asyncio.run(_run())


if __name__ == "__main__":
    main()
```

### `Dockerfile`
```dockerfile
FROM python:3.11-slim AS base

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

EXPOSE 8080

ENTRYPOINT ["mcp-artifacts"]
```

### `docker-compose.yml`
```yaml
version: "3.9"

services:
  artifacts-mcp:
    build: .
    container_name: mcp-artifacts
    environment:
      - AWS_REGION=${AWS_REGION:-us-east-1}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
      - DYNAMODB_TABLE=qitp_artifacts
      - S3_BUCKET=qitp-artifacts
    ports:
      - "8080:8080"
    restart: unless-stopped

  # Local development: LocalStack for S3 + DynamoDB
  localstack:
    image: localstack/localstack:3
    container_name: qitp-localstack-artifacts
    ports:
      - "4566:4566"
    environment:
      - SERVICES=s3,dynamodb
      - DEFAULT_REGION=us-east-1
    volumes:
      - localstack-data:/var/lib/localstack

volumes:
  localstack-data:
```

### `tests/conftest.py`
```python
"""Shared fixtures for artifact MCP tests."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from mcp_artifacts.catalog import ArtifactCatalog
from mcp_artifacts.storage import ArtifactStorage

BUCKET_NAME = "qitp-artifacts"
TABLE_NAME = "qitp_artifacts"
REGION = "us-east-1"


@pytest.fixture()
def aws_env(monkeypatch):
    """Set dummy AWS env vars for moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture()
def mock_s3(aws_env):
    """Provide a mocked S3 client with the artifacts bucket created."""
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET_NAME)
        storage = ArtifactStorage(s3_client=s3, bucket=BUCKET_NAME)
        yield storage


@pytest.fixture()
def mock_dynamodb(aws_env):
    """Provide a mocked DynamoDB resource with the artifacts table created."""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=REGION)
        ArtifactCatalog.ensure_table(dynamodb_resource=ddb, table_name=TABLE_NAME)
        catalog = ArtifactCatalog(dynamodb_resource=ddb, table_name=TABLE_NAME)
        yield catalog


@pytest.fixture()
def mock_aws_all(aws_env):
    """Provide both mocked S3 and DynamoDB together (same mock context)."""
    with mock_aws():
        s3 = boto3.client("s3", region_name=REGION)
        s3.create_bucket(Bucket=BUCKET_NAME)
        storage = ArtifactStorage(s3_client=s3, bucket=BUCKET_NAME)

        ddb = boto3.resource("dynamodb", region_name=REGION)
        ArtifactCatalog.ensure_table(dynamodb_resource=ddb, table_name=TABLE_NAME)
        catalog = ArtifactCatalog(dynamodb_resource=ddb, table_name=TABLE_NAME)

        yield storage, catalog
```

### `tests/test_create.py`
```python
"""Tests for create_artifact tool."""

from __future__ import annotations

import json

import pytest

from mcp_artifacts.tools.create import create_artifact


@pytest.mark.asyncio
async def test_create_report(mock_aws_all):
    """Create a report artifact and verify S3 + DynamoDB state."""
    storage, catalog = mock_aws_all

    result = await create_artifact(
        type="report",
        content="# My Report\n\nSome analysis here.",
        metadata={"title": "Q1 Analysis"},
        agent_id="research-agent",
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["artifact_id"]
    assert result["s3_key"].endswith("/artifact.md")

    # Verify DynamoDB entry
    entry = catalog.get_entry(result["artifact_id"])
    assert entry is not None
    assert entry["status"] == "ready"
    assert entry["type"] == "report"
    assert entry["agent_id"] == "research-agent"


@pytest.mark.asyncio
async def test_create_chart(mock_aws_all):
    """Create a chart artifact (JSX content)."""
    storage, catalog = mock_aws_all

    jsx_content = "<BarChart data={data}><Bar dataKey='value' /></BarChart>"
    result = await create_artifact(
        type="chart",
        content=jsx_content,
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["s3_key"].endswith("/artifact.jsx")


@pytest.mark.asyncio
async def test_create_backtest_result(mock_aws_all):
    """Create a backtest_result artifact (JSON content)."""
    storage, catalog = mock_aws_all

    content = json.dumps({"sharpe_ratio": 1.5, "max_drawdown": -0.12})
    result = await create_artifact(
        type="backtest_result",
        content=content,
        metadata={"strategy": "momentum"},
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["s3_key"].endswith("/artifact.json")


@pytest.mark.asyncio
async def test_create_image(mock_aws_all):
    """Create an image artifact (base64 content)."""
    import base64

    storage, catalog = mock_aws_all

    # Minimal 1x1 PNG
    fake_png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50).decode()
    result = await create_artifact(
        type="image",
        content=fake_png,
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["s3_key"].endswith("/artifact.png")


@pytest.mark.asyncio
async def test_create_data_export(mock_aws_all):
    """Create a data_export artifact (CSV content)."""
    storage, catalog = mock_aws_all

    csv_content = "date,symbol,close\n2025-01-01,AAPL,195.50\n2025-01-02,AAPL,196.10"
    result = await create_artifact(
        type="data_export",
        content=csv_content,
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["s3_key"].endswith("/artifact.csv")


@pytest.mark.asyncio
async def test_create_recommendation(mock_aws_all):
    """Create a recommendation artifact."""
    storage, catalog = mock_aws_all

    content = json.dumps({
        "action": "BUY",
        "symbol": "AAPL",
        "confidence": 0.85,
        "rationale": "Strong momentum signals",
    })
    result = await create_artifact(
        type="recommendation",
        content=content,
        agent_id="signal-agent",
        execution_id="exec-001",
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["s3_key"].endswith("/artifact.json")

    entry = catalog.get_entry(result["artifact_id"])
    assert entry["agent_id"] == "signal-agent"
    assert entry["execution_id"] == "exec-001"


@pytest.mark.asyncio
async def test_create_invalid_type(mock_aws_all):
    """Invalid artifact type raises ValueError."""
    storage, catalog = mock_aws_all

    with pytest.raises(ValueError):
        await create_artifact(
            type="invalid_type",
            content="stuff",
            storage=storage,
            catalog=catalog,
        )
```

### `tests/test_get.py`
```python
"""Tests for get_artifact and poll_artifact tools."""

from __future__ import annotations

import pytest

from mcp_artifacts.tools.create import create_artifact
from mcp_artifacts.tools.get import get_artifact
from mcp_artifacts.tools.poll import poll_artifact


@pytest.mark.asyncio
async def test_get_ready_artifact(mock_aws_all):
    """get_artifact returns signed URL for a ready artifact."""
    storage, catalog = mock_aws_all

    created = await create_artifact(
        type="report",
        content="# Report",
        storage=storage,
        catalog=catalog,
    )

    result = await get_artifact(
        artifact_id=created["artifact_id"],
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["signed_url"] is not None
    assert "qitp-artifacts" in result["signed_url"]
    assert result["type"] == "report"


@pytest.mark.asyncio
async def test_get_not_found(mock_aws_all):
    """get_artifact returns not_found for missing artifact."""
    storage, catalog = mock_aws_all

    result = await get_artifact(
        artifact_id="nonexistent-id",
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "not_found"
    assert result["signed_url"] is None


@pytest.mark.asyncio
async def test_get_processing_artifact(mock_aws_all):
    """get_artifact returns processing status without URL."""
    storage, catalog = mock_aws_all

    # Manually create a processing entry (no S3 upload)
    catalog.create_entry(
        artifact_id="test-processing-id",
        artifact_type="chart",
        s3_key="test-processing-id/artifact.jsx",
    )

    result = await get_artifact(
        artifact_id="test-processing-id",
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "processing"
    assert result["signed_url"] is None


@pytest.mark.asyncio
async def test_poll_ready_artifact(mock_aws_all):
    """poll_artifact returns immediately if artifact is already ready."""
    storage, catalog = mock_aws_all

    created = await create_artifact(
        type="report",
        content="# Report",
        storage=storage,
        catalog=catalog,
    )

    result = await poll_artifact(
        artifact_id=created["artifact_id"],
        timeout_s=5,
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "ready"
    assert result["signed_url"] is not None


@pytest.mark.asyncio
async def test_poll_not_found(mock_aws_all):
    """poll_artifact returns not_found immediately."""
    storage, catalog = mock_aws_all

    result = await poll_artifact(
        artifact_id="nonexistent",
        timeout_s=2,
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_poll_error_artifact(mock_aws_all):
    """poll_artifact returns error status immediately."""
    storage, catalog = mock_aws_all

    catalog.create_entry(
        artifact_id="error-artifact",
        artifact_type="report",
        s3_key="error-artifact/artifact.md",
    )
    catalog.update_status("error-artifact", "error")

    result = await poll_artifact(
        artifact_id="error-artifact",
        timeout_s=5,
        storage=storage,
        catalog=catalog,
    )

    assert result["status"] == "error"
    assert result["signed_url"] is None
```

### `tests/test_catalog.py`
```python
"""Tests for DynamoDB catalog operations."""

from __future__ import annotations

import pytest

from mcp_artifacts.catalog import ArtifactCatalog
from mcp_artifacts.tools.create import create_artifact
from mcp_artifacts.tools.list_artifacts import list_artifacts


@pytest.mark.asyncio
async def test_list_by_type(mock_aws_all):
    """list_artifacts filters by artifact type."""
    storage, catalog = mock_aws_all

    await create_artifact(type="report", content="# R1", storage=storage, catalog=catalog)
    await create_artifact(type="report", content="# R2", storage=storage, catalog=catalog)
    await create_artifact(type="chart", content="<Chart/>", storage=storage, catalog=catalog)

    results = await list_artifacts(type="report", catalog=catalog)
    assert len(results) == 2
    assert all(r["type"] == "report" for r in results)


@pytest.mark.asyncio
async def test_list_by_agent_id(mock_aws_all):
    """list_artifacts filters by agent_id."""
    storage, catalog = mock_aws_all

    await create_artifact(
        type="report", content="# R1", agent_id="agent-a", storage=storage, catalog=catalog
    )
    await create_artifact(
        type="chart", content="<C/>", agent_id="agent-b", storage=storage, catalog=catalog
    )
    await create_artifact(
        type="report", content="# R2", agent_id="agent-a", storage=storage, catalog=catalog
    )

    results = await list_artifacts(agent_id="agent-a", catalog=catalog)
    assert len(results) == 2
    assert all(r["agent_id"] == "agent-a" for r in results)


@pytest.mark.asyncio
async def test_list_with_limit(mock_aws_all):
    """list_artifacts respects the limit parameter."""
    storage, catalog = mock_aws_all

    for i in range(5):
        await create_artifact(type="report", content=f"# R{i}", storage=storage, catalog=catalog)

    results = await list_artifacts(type="report", limit=3, catalog=catalog)
    assert len(results) <= 3


@pytest.mark.asyncio
async def test_list_no_filters(mock_aws_all):
    """list_artifacts with no filters returns all (scan)."""
    storage, catalog = mock_aws_all

    await create_artifact(type="report", content="# R", storage=storage, catalog=catalog)
    await create_artifact(type="chart", content="<C/>", storage=storage, catalog=catalog)

    results = await list_artifacts(catalog=catalog)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_catalog_create_and_get(mock_aws_all):
    """Direct catalog create + get roundtrip."""
    _, catalog = mock_aws_all

    catalog.create_entry(
        artifact_id="test-123",
        artifact_type="report",
        s3_key="test-123/artifact.md",
        agent_id="agent-x",
        metadata={"key": "value"},
    )

    entry = catalog.get_entry("test-123")
    assert entry is not None
    assert entry["artifact_id"] == "test-123"
    assert entry["type"] == "report"
    assert entry["status"] == "processing"
    assert entry["agent_id"] == "agent-x"
    assert entry["metadata"] == {"key": "value"}


@pytest.mark.asyncio
async def test_catalog_update_status(mock_aws_all):
    """Catalog status update works."""
    _, catalog = mock_aws_all

    catalog.create_entry(
        artifact_id="test-456",
        artifact_type="chart",
        s3_key="test-456/artifact.jsx",
    )

    catalog.update_status("test-456", "ready")
    entry = catalog.get_entry("test-456")
    assert entry["status"] == "ready"

    catalog.update_status("test-456", "error")
    entry = catalog.get_entry("test-456")
    assert entry["status"] == "error"
```

---

## Implementation Details

### Tools (4 from Doc 6)

1. **`create_artifact(type, content, metadata)`** returns `CreateResult`
   - type: ArtifactType enum (chart, report, backtest_result, recommendation, image, data_export)
   - Stores content to S3 at `s3://qitp-artifacts/{artifact_id}/{filename}`
   - Creates DynamoDB catalog entry with status=processing
   - Uploads to S3, then updates status to ready
   - On failure, sets status to error
   - Returns artifact_id immediately

2. **`get_artifact(artifact_id)`** returns `ArtifactResult`
   - Returns signed URL if ready (status=ready)
   - Returns current status if not ready (processing/error)
   - Returns not_found if artifact_id does not exist

3. **`poll_artifact(artifact_id, timeout_s=60)`** returns `ArtifactResult`
   - Polls DynamoDB every 2s until artifact is ready or timeout
   - Returns signed URL when ready
   - Returns immediately for ready, error, or not_found states

4. **`list_artifacts(type?, agent_id?, date?, limit=50)`** returns `list[ArtifactMeta]`
   - Query DynamoDB with filters via GSIs
   - Returns metadata only, not content or URLs

### DynamoDB Table: `qitp_artifacts`
| Attribute | Type | Role |
|-----------|------|------|
| artifact_id | S | Partition Key (UUID) |
| type | S | GSI1 PK |
| created_at | S | GSI1 SK, GSI2 SK (ISO 8601) |
| agent_id | S | GSI2 PK |
| status | S | processing / ready / error |
| s3_key | S | Full S3 key path |
| execution_id | S | Optional execution reference |
| metadata | S | JSON-encoded dict |

**GSI1:** `type-created_at-index` (PK=type, SK=created_at)
**GSI2:** `agent_id-created_at-index` (PK=agent_id, SK=created_at)

### S3 Bucket: `qitp-artifacts`
- Key pattern: `{artifact_id}/{filename}`
- Signed URL expiry: 1 hour (3600 seconds)

### Content Handling by Type
| Type | Extension | Content-Type | Input |
|------|-----------|-------------|-------|
| chart | .jsx | text/jsx | React JSX string |
| report | .md | text/markdown | Markdown string |
| backtest_result | .json | application/json | JSON string |
| recommendation | .json | application/json | JSON string |
| image | .png | image/png | Base64 string (decoded before upload) |
| data_export | .csv | text/csv | CSV string |

## Acceptance Criteria
- [ ] create_artifact stores content to S3 and creates DynamoDB entry
- [ ] get_artifact returns signed URL for ready artifacts
- [ ] poll_artifact waits and returns when artifact becomes ready
- [ ] list_artifacts filters correctly by type, agent_id, date
- [ ] Signed URLs are valid and expire after 1 hour
- [ ] All 6 artifact types handled correctly
- [ ] Docker build succeeds

## Test Plan
```bash
cd ~/dev/tccw-mcp-artifacts
pip install -e ".[dev]"
pytest -v
docker build -t mcp-artifacts .
```

## Agent Instructions
This is the universal output pipeline — every agent in the system creates artifacts through this MCP. Keep it simple and reliable. Use boto3 for S3/DynamoDB. Mock AWS services in tests with moto. The signed URL generation is critical for the Claude UI integration.
