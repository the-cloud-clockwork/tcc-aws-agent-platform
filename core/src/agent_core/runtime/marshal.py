"""Output marshalling with mandatory S3 artifact storage + DynamoDB catalog."""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Tool names whose toolUse.input wraps the typed payload under a "content" key.
# StructuredOutputEnforcer's synthetic toolUse uses the schema class name and
# its input IS the typed payload — those are handled in the else branch.
_KNOWN_TOOL_PASSTHROUGH = {"create_artifact"}

_FENCED_JSON_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _parse_fenced_json(text: str) -> dict[str, Any] | None:
    """Return the first parseable JSON object from a ```json``` code fence."""
    for match in _FENCED_JSON_RE.finditer(text):
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _extract_typed_payload(envelope: dict[str, Any]) -> dict[str, Any] | None:
    """Best-effort extraction of a typed payload from a Strands envelope.

    Priority:
      1. Last assistant message's toolUse.input — either the StructuredOutput
         Enforcer's synthetic block (input == typed payload) or a
         create_artifact tool call (input.content == typed payload).
      2. Fenced ```json``` block in any text content of the last message.
      3. None — caller falls back to the envelope itself.

    Multiagent envelopes (type == "multiagent_result") are skipped — caller
    falls back to envelope. Single-agent extraction is v1 scope.
    """
    if envelope.get("type") == "multiagent_result":
        return None

    message = envelope.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, list):
        return None

    for block in reversed(content):
        if not isinstance(block, dict):
            continue
        tool_use = block.get("toolUse")
        if not isinstance(tool_use, dict):
            continue
        input_ = tool_use.get("input")
        if not isinstance(input_, dict):
            continue
        name = tool_use.get("name")
        if name in _KNOWN_TOOL_PASSTHROUGH:
            inner = input_.get("content")
            if isinstance(inner, dict):
                return inner
            continue
        return input_

    for block in content:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if not isinstance(text, str):
            continue
        parsed = _parse_fenced_json(text)
        if parsed is not None:
            return parsed

    return None


def _serialize_result(result: Any) -> dict[str, Any]:
    """Convert an agent result to a plain dict, preferring typed payloads.

    For Strands AgentResult objects (which expose to_dict()), the wire envelope
    is searched for a typed payload before falling back to the envelope itself.
    See _extract_typed_payload for priority. This closes the soft-failure where
    domain-tier S3 artifacts stored the conversation envelope rather than the
    schema the agent produced.
    """
    if hasattr(result, "to_dict"):
        output = result.to_dict()
        if hasattr(output, "to_dict"):
            output = output.to_dict()
        if isinstance(output, dict):
            extracted = _extract_typed_payload(output)
            return extracted if extracted is not None else output
        return {"raw_output": str(output)}
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
