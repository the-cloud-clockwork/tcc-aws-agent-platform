"""REST API handler for artifacts.

Routes:
  POST /api/artifacts                    — Create artifact (S3 + DynamoDB)
  GET  /api/artifacts                    — List artifacts
  GET  /api/artifacts/{artifact_id}      — Get artifact metadata + signed URL
  GET  /api/artifacts/{artifact_id}/data — Get artifact content
  GET  /api/runs                         — List pipeline runs
  GET  /api/runs/{execution_id}          — Get manifest
  GET  /api/runs/{execution_id}/{agent}  — Get agent artifact from run
"""

import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Attr, Key

logger = logging.getLogger(__name__)


def _route(path: str, method: str, params: dict, body: dict | None = None) -> dict:
    """Match a request to the correct handler."""
    if path == "/api/artifacts" and method == "POST":
        return _create_artifact(body or {})
    if path == "/api/artifacts" and method == "GET":
        return _list_artifacts(params)
    if path.startswith("/api/artifacts/") and path.endswith("/data"):
        return _get_artifact_data(path.split("/")[3])
    if path.startswith("/api/artifacts/"):
        return _get_artifact(path.split("/")[3])
    if path == "/api/runs" and method == "GET":
        return _list_runs(params)
    if path.startswith("/api/runs/"):
        parts = path.split("/")
        execution_id = parts[3] if len(parts) > 3 else ""
        agent_id = parts[4] if len(parts) > 4 else ""
        return _get_run_agent(execution_id, agent_id) if agent_id else _get_run(execution_id)
    return _response(404, {"error": "Not found"})


def handler(event: dict, context) -> dict:
    """API Gateway Lambda proxy handler."""
    try:
        body = None
        if event.get("body"):
            body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
        return _route(
            event.get("path", ""),
            event.get("httpMethod", "GET"),
            event.get("queryStringParameters") or {},
            body=body,
        )
    except (KeyError, ValueError, IndexError) as exc:
        logger.warning("Bad request: %s", exc)
        return _response(400, {"error": str(exc)})
    except Exception as exc:
        logger.exception("Unhandled API error")
        return _response(500, {"error": str(exc)})


def _create_artifact(body: dict) -> dict:
    """Create an artifact: write metadata to DynamoDB and content to S3."""
    import uuid
    from datetime import datetime, timezone

    agent_id = body.get("agent_id", "unknown")
    artifact_type = body.get("artifact_type", "agent_output")
    content = body.get("content", {})
    claim_check = body.get("claim_check", False)

    artifact_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    s3_key = f"pipeline/{now.strftime('%Y-%m-%d')}/{artifact_id}/{agent_id}.json"

    s3 = boto3.client("s3")
    bucket = os.environ.get("ARTIFACTS_BUCKET", "")
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    s3.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=json.dumps(content, default=str).encode(),
        ContentType="application/json",
        ExpectedBucketOwner=account_id,
    )

    table = _get_table()
    item = {
        "artifact_id": artifact_id,
        "agent_id": agent_id,
        "type": artifact_type,
        "s3_key": s3_key,
        "created_at": now.isoformat(),
        "claim_check": claim_check,
    }
    if body.get("execution_id"):
        item["execution_id"] = body["execution_id"]
    if body.get("tier"):
        item["tier"] = body["tier"]

    table.put_item(Item=item)
    logger.info("Artifact created: %s (agent=%s)", artifact_id, agent_id)

    return _response(201, {"artifact_id": artifact_id, "s3_key": s3_key})


def _list_artifacts(params: dict) -> dict:
    """List artifacts using GSI queries when a single filter key matches a GSI."""
    table = _get_table()
    limit = int(params.get("limit", "50"))

    # Prefer GSI query over scan when a single primary filter is provided
    if "agent_id" in params and "type" not in params:
        result = table.query(
            IndexName="agent_id-created_at-index",
            KeyConditionExpression=Key("agent_id").eq(params["agent_id"]),
            ScanIndexForward=False,
            Limit=limit,
        )
    elif "type" in params and "agent_id" not in params:
        result = table.query(
            IndexName="type-created_at-index",
            KeyConditionExpression=Key("type").eq(params["type"]),
            ScanIndexForward=False,
            Limit=limit,
        )
    else:
        # Multi-filter or no filter — fall back to scan
        kwargs = {"Limit": limit}
        filters = []
        values = {}
        names = {}
        for key in ["agent_id", "type", "tier", "execution_id", "pipeline_date"]:
            if key in params:
                attr = f"#{key}"
                val = f":{key}"
                filters.append(f"{attr} = {val}")
                values[val] = params[key]
                names[attr] = key
        if filters:
            kwargs["FilterExpression"] = " AND ".join(filters)
            kwargs["ExpressionAttributeValues"] = values
            kwargs["ExpressionAttributeNames"] = names
        result = table.scan(**kwargs)

    return _response(
        200, {"artifacts": result.get("Items", []), "count": result.get("Count", 0)}
    )


def _get_artifact(artifact_id: str) -> dict:
    table = _get_table()
    result = table.get_item(Key={"artifact_id": artifact_id})
    item = result.get("Item")
    if not item:
        return _response(404, {"error": "Artifact not found"})
    item["signed_url"] = _get_signed_url(item.get("s3_key", ""))
    return _response(200, item)


def _get_artifact_data(artifact_id: str) -> dict:
    table = _get_table()
    result = table.get_item(Key={"artifact_id": artifact_id})
    item = result.get("Item")
    if not item:
        return _response(404, {"error": "Artifact not found"})
    s3 = boto3.client("s3")
    bucket = os.environ.get("ARTIFACTS_BUCKET", "")
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    obj = s3.get_object(Bucket=bucket, Key=item["s3_key"], ExpectedBucketOwner=account_id)
    content = json.loads(obj["Body"].read().decode("utf-8"))
    return _response(200, content)


def _list_runs(params: dict) -> dict:
    """List pipeline runs using the type-created_at GSI."""
    table = _get_table()
    limit = int(params.get("limit", "20"))

    result = table.query(
        IndexName="type-created_at-index",
        KeyConditionExpression=Key("type").eq("pipeline_run"),
        ScanIndexForward=False,
        Limit=limit,
    )
    return _response(
        200, {"runs": result.get("Items", []), "count": result.get("Count", 0)}
    )


def _get_run(execution_id: str) -> dict:
    """Get a pipeline run by execution_id using the execution_id-agent_id GSI."""
    table = _get_table()

    result = table.query(
        IndexName="execution_id-agent_id-index",
        KeyConditionExpression=Key("execution_id").eq(execution_id),
        FilterExpression=Attr("type").eq("pipeline_run"),
    )
    items = result.get("Items", [])
    if not items:
        return _response(404, {"error": "Run not found"})
    item = items[0]
    s3 = boto3.client("s3")
    bucket = os.environ.get("ARTIFACTS_BUCKET", "")
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    try:
        obj = s3.get_object(Bucket=bucket, Key=item["s3_key"], ExpectedBucketOwner=account_id)
        item["manifest"] = json.loads(obj["Body"].read().decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        logger.warning("Manifest S3 key not found: %s", item.get("s3_key"))
    except json.JSONDecodeError as exc:
        logger.warning("Invalid manifest JSON for %s: %s", item.get("s3_key"), exc)
    except Exception as exc:
        logger.warning("Failed to fetch manifest for %s: %s", item.get("s3_key"), exc)
    return _response(200, item)


def _get_run_agent(execution_id: str, agent_id: str) -> dict:
    """Get an agent artifact from a run using the execution_id-agent_id GSI."""
    table = _get_table()

    result = table.query(
        IndexName="execution_id-agent_id-index",
        KeyConditionExpression=Key("execution_id").eq(execution_id)
        & Key("agent_id").eq(agent_id),
    )
    items = result.get("Items", [])
    if not items:
        return _response(404, {"error": "Agent artifact not found"})
    item = items[0]
    item["signed_url"] = _get_signed_url(item.get("s3_key", ""))
    return _response(200, item)


def _get_table():
    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(os.environ["ARTIFACTS_TABLE"])


def _get_signed_url(s3_key: str) -> str:
    if not s3_key:
        return ""
    s3 = boto3.client("s3")
    bucket = os.environ.get("ARTIFACTS_BUCKET", "")
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=3600,
    )


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body, default=str),
    }
