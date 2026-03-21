"""REST API handler for artifact retrieval.

Routes:
  GET /api/artifacts                     — List artifacts
  GET /api/artifacts/{artifact_id}       — Get artifact metadata + signed URL
  GET /api/artifacts/{artifact_id}/data  — Get artifact content
  GET /api/runs                          — List pipeline runs
  GET /api/runs/{execution_id}           — Get manifest
  GET /api/runs/{execution_id}/{agent}   — Get agent artifact from run
"""

import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)


def handler(event: dict, context) -> dict:
    """API Gateway Lambda proxy handler."""
    path = event.get("path", "")
    method = event.get("httpMethod", "GET")
    params = event.get("queryStringParameters") or {}

    try:
        if path == "/api/artifacts" and method == "GET":
            return _list_artifacts(params)
        elif path.startswith("/api/artifacts/") and path.endswith("/data"):
            artifact_id = path.split("/")[3]
            return _get_artifact_data(artifact_id)
        elif path.startswith("/api/artifacts/"):
            artifact_id = path.split("/")[3]
            return _get_artifact(artifact_id)
        elif path == "/api/runs" and method == "GET":
            return _list_runs(params)
        elif path.startswith("/api/runs/"):
            parts = path.split("/")
            execution_id = parts[3] if len(parts) > 3 else ""
            agent_id = parts[4] if len(parts) > 4 else ""
            if agent_id:
                return _get_run_agent(execution_id, agent_id)
            return _get_run(execution_id)
        else:
            return _response(404, {"error": "Not found"})
    except (KeyError, ValueError, IndexError) as exc:
        logger.warning("Bad request: %s", exc)
        return _response(400, {"error": str(exc)})
    except Exception as exc:
        logger.exception("Unhandled API error")
        return _response(500, {"error": str(exc)})


def _list_artifacts(params: dict) -> dict:
    table = _get_table()
    kwargs = {"Limit": int(params.get("limit", "50"))}
    # Build filter expressions from params (date, agent_id, type, tier, execution_id)
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
    # Generate signed URL
    item["signed_url"] = _get_signed_url(item.get("s3_key", ""))
    return _response(200, item)


def _get_artifact_data(artifact_id: str) -> dict:
    table = _get_table()
    result = table.get_item(Key={"artifact_id": artifact_id})
    item = result.get("Item")
    if not item:
        return _response(404, {"error": "Artifact not found"})
    # Fetch content from S3
    s3 = boto3.client("s3")
    bucket = os.environ.get("ARTIFACTS_BUCKET", "")
    obj = s3.get_object(Bucket=bucket, Key=item["s3_key"])
    content = json.loads(obj["Body"].read().decode("utf-8"))
    return _response(200, content)


def _list_runs(params: dict) -> dict:
    table = _get_table()
    result = table.scan(
        FilterExpression="#t = :t",
        ExpressionAttributeNames={"#t": "type"},
        ExpressionAttributeValues={":t": "pipeline_run"},
        Limit=int(params.get("limit", "20")),
    )
    items = sorted(
        result.get("Items", []), key=lambda x: x.get("created_at", ""), reverse=True
    )
    return _response(200, {"runs": items, "count": len(items)})


def _get_run(execution_id: str) -> dict:
    table = _get_table()
    result = table.scan(
        FilterExpression="execution_id = :eid AND #t = :t",
        ExpressionAttributeNames={"#t": "type"},
        ExpressionAttributeValues={":eid": execution_id, ":t": "pipeline_run"},
    )
    items = result.get("Items", [])
    if not items:
        return _response(404, {"error": "Run not found"})
    item = items[0]
    # Fetch manifest content
    s3 = boto3.client("s3")
    bucket = os.environ.get("ARTIFACTS_BUCKET", "")
    try:
        obj = s3.get_object(Bucket=bucket, Key=item["s3_key"])
        item["manifest"] = json.loads(obj["Body"].read().decode("utf-8"))
    except s3.exceptions.NoSuchKey:
        logger.warning("Manifest S3 key not found: %s", item.get("s3_key"))
    except json.JSONDecodeError as exc:
        logger.warning("Invalid manifest JSON for %s: %s", item.get("s3_key"), exc)
    except Exception as exc:
        logger.warning("Failed to fetch manifest for %s: %s", item.get("s3_key"), exc)
    return _response(200, item)


def _get_run_agent(execution_id: str, agent_id: str) -> dict:
    table = _get_table()
    result = table.scan(
        FilterExpression="execution_id = :eid AND agent_id = :aid",
        ExpressionAttributeValues={":eid": execution_id, ":aid": agent_id},
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
            "Access-Control-Allow-Methods": "GET,OPTIONS",
        },
        "body": json.dumps(body, default=str),
    }
