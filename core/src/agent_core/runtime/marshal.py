"""Output marshalling with S3 claim-check for Step Functions 256KB limit."""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)

MAX_OUTPUT_BYTES = 256 * 1024


def marshal_output(
    result: Any,
    agent_id: str,
    execution_id: str,
    max_bytes: int = MAX_OUTPUT_BYTES,
    s3_bucket: str | None = None,
) -> dict[str, Any]:
    """Convert agent result to dict, with S3 claim-check on overflow.

    Args:
        result: Agent output (Pydantic model, dict, or str).
        agent_id: Agent identifier for S3 key prefix.
        execution_id: Execution/session ID for S3 key.
        max_bytes: Overflow threshold (default 256KB).
        s3_bucket: S3 bucket for claim-check. Falls back to ARTIFACTS_BUCKET env var.

    Returns:
        JSON-serializable dict. If overflowed, contains claim_check reference.
    """
    # MultiAgentResult from Swarm or Graph — both have .to_dict() + .status
    if hasattr(result, "to_dict") and hasattr(result, "status"):
        output = result.to_dict()
    elif hasattr(result, "model_dump"):
        output = result.model_dump()
    elif isinstance(result, dict):
        output = result
    else:
        try:
            output = json.loads(str(result))
        except (json.JSONDecodeError, TypeError):
            output = {"raw_output": str(result)}

    serialized = json.dumps(output, default=str)

    if len(serialized.encode("utf-8")) <= max_bytes:
        return output

    # Overflow — upload to S3
    bucket = s3_bucket or os.environ.get("ARTIFACTS_BUCKET")
    if not bucket:
        logger.warning("Output exceeds %d bytes but no S3 bucket configured — truncating", max_bytes)
        return {
            "claim_check": True,
            "artifact_id": None,
            "_overflow_warning": "No ARTIFACTS_BUCKET configured. Output truncated.",
        }

    s3_key = f"claim-check/{agent_id}/{execution_id}/{uuid.uuid4().hex}.json"
    try:
        import boto3
        s3 = boto3.client("s3")
        s3.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=serialized.encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("Claim-check uploaded: s3://%s/%s (%d bytes)", bucket, s3_key, len(serialized))
        return {
            "claim_check": True,
            "artifact_id": s3_key,
            "bucket": bucket,
            "message": "Output exceeded 256KB. Full result stored as artifact.",
        }
    except Exception:
        logger.exception("Failed to upload claim-check to S3")
        return {
            "claim_check": True,
            "artifact_id": None,
            "_overflow_warning": "S3 upload failed. Output truncated.",
        }
