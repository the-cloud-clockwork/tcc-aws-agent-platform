"""Manifest generation for pipeline runs.

Generates _manifest.json — an index of all artifacts from a pipeline execution.
Called as the final step in Step Functions workflow.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    """Generate and store pipeline manifest.

    Input (from SFN state):
        $.execution_id: str — SFN execution ID
        $.pipeline: str — pipeline name (e.g., "weekly-analysis")
        $.date: str — analysis date (e.g., "2024-11-04")
        $.results: dict — per-agent results with artifact_id, s3_key, success
        $.started_at: str — ISO timestamp of pipeline start

    Returns:
        dict with manifest artifact_id and s3_key
    """
    execution_id = event.get("execution_id", f"exec-{uuid.uuid4().hex[:8]}")
    pipeline = event.get("pipeline", "unknown")
    date = event.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    results = event.get("results", {})
    started_at = event.get("started_at", "")

    completed_at = datetime.now(timezone.utc).isoformat()

    # Calculate duration if started_at provided
    duration_seconds = 0
    if started_at:
        try:
            start = datetime.fromisoformat(started_at)
            duration_seconds = int((datetime.now(timezone.utc) - start).total_seconds())
        except (ValueError, TypeError):
            pass

    # Build agent summary from results
    agents = {}
    succeeded = 0
    failed = 0
    for agent_name, agent_result in results.items():
        if isinstance(agent_result, dict):
            success = agent_result.get("success", False)
            agents[agent_name] = {
                "artifact_id": agent_result.get("artifact_id", ""),
                "s3_key": agent_result.get("s3_key", ""),
                "success": success,
            }
            if not success:
                agents[agent_name]["error"] = agent_result.get("error", "unknown")
                failed += 1
            else:
                succeeded += 1
        else:
            agents[agent_name] = {"artifact_id": "", "s3_key": "", "success": False, "error": "invalid_result"}
            failed += 1

    manifest = {
        "execution_id": execution_id,
        "pipeline": pipeline,
        "date": date,
        "completed_at": completed_at,
        "duration_seconds": duration_seconds,
        "agents": agents,
        "summary": {
            "total_agents": len(agents),
            "succeeded": succeeded,
            "failed": failed,
        },
    }

    # Upload to S3
    bucket = os.environ.get("ARTIFACTS_BUCKET", "")
    s3_key = f"platform/{date}/{execution_id}/_manifest.json"
    artifact_id = str(uuid.uuid4())

    if bucket:
        try:
            s3 = boto3.client("s3")
            account_id = boto3.client("sts").get_caller_identity()["Account"]
            s3.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=json.dumps(manifest, indent=2),
                ContentType="application/json",
                ExpectedBucketOwner=account_id,
            )
            logger.info("Manifest stored: s3://%s/%s", bucket, s3_key)
        except Exception as e:
            logger.error("Failed to store manifest: %s", e)
            return {"artifact_id": "", "s3_key": "", "success": False, "error": str(e)}
    else:
        logger.warning("No ARTIFACTS_BUCKET configured, manifest not stored")
        return {"artifact_id": "", "s3_key": "", "success": False, "error": "no_bucket"}

    # Register in DynamoDB catalog
    table_name = os.environ.get("ARTIFACTS_TABLE", "")
    if table_name:
        try:
            dynamodb = boto3.resource("dynamodb")
            table = dynamodb.Table(table_name)
            table.put_item(Item={
                "artifact_id": artifact_id,
                "type": "pipeline_run",
                "status": "ready",
                "s3_key": s3_key,
                "agent_id": "_manifest",
                "execution_id": execution_id,
                "tier": "platform",
                "pipeline_date": date,
                "created_at": completed_at,
                "metadata": {
                    "pipeline": pipeline,
                    "total_agents": len(agents),
                    "succeeded": succeeded,
                    "failed": failed,
                },
            })
        except Exception as e:
            logger.error("Failed to register manifest in catalog: %s", e)

    return {
        "artifact_id": artifact_id,
        "s3_key": s3_key,
        "success": True,
        "manifest": manifest,
    }
