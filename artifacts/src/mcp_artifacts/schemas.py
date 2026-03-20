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
    SIMULATION_RESULT = "simulation_result"
    RECOMMENDATION = "recommendation"
    IMAGE = "image"
    DATA_EXPORT = "data_export"
    PIPELINE_RUN = "pipeline_run"


# Map artifact type to file extension and content-type
ARTIFACT_TYPE_MAP: dict[ArtifactType, tuple[str, str]] = {
    ArtifactType.CHART: (".jsx", "text/jsx"),
    ArtifactType.REPORT: (".md", "text/markdown"),
    ArtifactType.SIMULATION_RESULT: (".json", "application/json"),
    ArtifactType.RECOMMENDATION: (".json", "application/json"),
    ArtifactType.IMAGE: (".png", "image/png"),
    ArtifactType.DATA_EXPORT: (".csv", "text/csv"),
    ArtifactType.PIPELINE_RUN: (".json", "application/json"),
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
    tier: str = "platform"
    kms_key_alias: str | None = None
    pipeline_date: str = ""


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
