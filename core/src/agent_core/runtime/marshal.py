"""Output marshalling with mandatory S3 artifact storage + DynamoDB catalog."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _serialize_result(result: Any) -> dict[str, Any]:
    """Convert an agent result to a plain dict."""
    if hasattr(result, "to_dict"):
        output = result.to_dict()
        if hasattr(output, "to_dict"):
            output = output.to_dict()
        return output if isinstance(output, dict) else {"raw_output": str(output)}
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, dict):
        try:
            return dict(result)
        except TypeError:
            if hasattr(result, "__getitem__"):
                return {k: result[k] for k in result}
            return {"raw_output": str(result)}
    try:
        return json.loads(str(result))
    except (json.JSONDecodeError, TypeError):
        return {"raw_output": str(result)}


def _register_catalog(
    artifact_id: str,
    agent_id: str,
    execution_id: str,
    s3_key: str,
    bucket: str,
    tier: str,
    kms_key_alias: str | None,
    date: str,
) -> None:
    """Register artifact in DynamoDB catalog. Non-fatal on failure."""
    table_name = os.environ.get("ARTIFACTS_TABLE", "")
    if not table_name:
        return

    try:
        import boto3

        ddb = boto3.resource("dynamodb")
        table = ddb.Table(table_name)
        now = datetime.now(timezone.utc).isoformat()
        table.put_item(Item={
            "artifact_id": artifact_id,
            "agent_id": agent_id,
            "execution_id": execution_id,
            "artifact_type": "agent_output",
            "s3_key": s3_key,
            "s3_bucket": bucket,
            "tier": tier,
            "status": "ready",
            "content_type": "application/json",
            "created_at": now,
            "updated_at": now,
            "pipeline_date": date,
            "kms_key_alias": kms_key_alias or "",
            "claim_check": True,
        })
        logger.info("Artifact %s registered in catalog (%s)", artifact_id, table_name)
    except Exception as err:
        logger.warning("Failed to register artifact %s in catalog: %s", artifact_id, err)


def marshal_output(
    result: Any,
    agent_id: str,
    execution_id: str,
    s3_bucket: str | None = None,
    tier: str = "platform",
    kms_key_alias: str | None = None,
    date: str | None = None,
) -> dict[str, Any]:
    """Convert agent result to dict, upload to S3, register in DynamoDB catalog.

    Every agent execution produces a JSON artifact in S3 + a DynamoDB catalog
    entry — unconditionally. Artifacts are the source of truth.

    Args:
        result: Agent output (Pydantic model, dict, or str).
        agent_id: Agent identifier for S3 key prefix.
        execution_id: Execution/session ID for S3 key.
        s3_bucket: S3 bucket for storage. Falls back to ARTIFACTS_BUCKET env var.
        tier: Storage tier — "platform" or "domain".
        kms_key_alias: KMS key alias for server-side encryption (optional).
        date: Analysis date (YYYY-MM-DD). Defaults to today.

    Returns:
        JSON-serializable dict with artifact_id, s3_key, bucket, tier, and output.
    """
    output = _serialize_result(result)
    serialized = json.dumps(output, default=str)

    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not execution_id:
        execution_id = f"exec-{uuid.uuid4().hex[:8]}"

    bucket = s3_bucket or os.environ.get("ARTIFACTS_BUCKET")
    if not bucket:
        logger.warning("No ARTIFACTS_BUCKET configured — artifact not stored")
        return {
            "artifact_id": "",
            "s3_key": "",
            "bucket": "",
            "tier": tier,
            "agent_id": agent_id,
            "success": False,
            "error": "no_bucket",
            "output": output,
        }

    artifact_id = str(uuid.uuid4())
    s3_key = f"{tier}/{date}/{execution_id}/{agent_id}.json"

    try:
        import boto3

        sts = boto3.client("sts")
        account_id = sts.get_caller_identity()["Account"]

        put_kwargs: dict[str, Any] = {
            "Bucket": bucket,
            "Key": s3_key,
            "Body": serialized.encode("utf-8"),
            "ContentType": "application/json",
            "ExpectedBucketOwner": account_id,
        }
        if kms_key_alias:
            put_kwargs["ServerSideEncryption"] = "aws:kms"
            put_kwargs["SSEKMSKeyId"] = kms_key_alias

        s3 = boto3.client("s3")
        s3.put_object(**put_kwargs)
        logger.info(
            "Artifact stored: s3://%s/%s (%d bytes, tier=%s)",
            bucket, s3_key, len(serialized), tier,
        )

        # Mandatory: register in DynamoDB catalog
        _register_catalog(
            artifact_id=artifact_id,
            agent_id=agent_id,
            execution_id=execution_id,
            s3_key=s3_key,
            bucket=bucket,
            tier=tier,
            kms_key_alias=kms_key_alias,
            date=date,
        )

        return {
            "artifact_id": artifact_id,
            "s3_key": s3_key,
            "bucket": bucket,
            "tier": tier,
            "agent_id": agent_id,
            "success": True,
            "claim_check": True,
            "output": output,
        }
    except Exception as exc:
        logger.exception("Failed to upload artifact to S3")
        return {
            "artifact_id": "",
            "s3_key": "",
            "bucket": bucket,
            "tier": tier,
            "agent_id": agent_id,
            "success": False,
            "error": str(exc),
            "output": output,
        }
