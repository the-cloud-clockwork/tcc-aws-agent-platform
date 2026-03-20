"""create_artifact tool implementation."""

from __future__ import annotations

import os
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
    idempotency_key: str | None = None,
    tier: str = "platform",
    kms_key_alias: str | None = None,
    pipeline_date: str = "",
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
    idempotency_key:
        Optional key to prevent duplicate artifact creation.
        If an artifact with this key already exists, returns the existing
        artifact instead of creating a new one.
        Format: {agent_id}:{execution_id}:{operation}:{param_hash}
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

    # Idempotency check: look up existing artifact by key
    if idempotency_key is not None:
        existing = _catalog.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            result = CreateResult(
                artifact_id=existing["artifact_id"],
                status=existing.get("status", "ready"),
                s3_key=existing.get("s3_key", ""),
            )
            return result.model_dump()

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
        idempotency_key=idempotency_key,
        tier=tier,
        kms_key_alias=kms_key_alias,
        pipeline_date=pipeline_date,
    )

    try:
        # 2. Upload content to S3
        body = encode_content(artifact_type, content)
        ct = content_type_for_type(artifact_type)
        extra_args = {}
        if kms_key_alias:
            kms_key_id = os.environ.get(
                f"KMS_KEY_ARN_{kms_key_alias.upper().replace('-', '_')}",
                kms_key_alias,
            )
            extra_args["ServerSideEncryption"] = "aws:kms"
            extra_args["SSEKMSKeyId"] = kms_key_id
        _storage.put_object(s3_key, body, ct, extra_args=extra_args)

        # 3. Update status to ready
        _catalog.update_status(artifact_id, "ready")
    except Exception:
        _catalog.update_status(artifact_id, "error")
        raise

    result = CreateResult(artifact_id=artifact_id, status="ready", s3_key=s3_key)
    return result.model_dump()
