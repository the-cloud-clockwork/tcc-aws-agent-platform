---
title: Artifacts
nav_order: 12
parent: SDK Reference
---

# Artifacts

The Artifacts subsystem implements the claim-check pattern for large agent outputs. Instead of passing large payloads through Step Functions state transitions or agent-to-agent messages, agents store outputs in S3 and pass lightweight artifact keys. Downstream consumers retrieve the full payload via a pre-signed URL.

The artifact store runs as a **Lambda-backed Gateway target** (not a standalone MCP server process). The Lambda handler is registered as a `lambda` target in the Gateway, so agents access it as an MCP tool through the standard Gateway connection.

> **Architecture guide:** [Tools, MCP & Gateway](../tools.md)

## MCP Tools

The artifact Lambda handler exposes exactly four MCP tools:

| Tool | Description |
|------|-------------|
| `create_artifact` | Store content in S3, register metadata in DynamoDB, return `artifact_id` and `signed_url` |
| `get_artifact` | Retrieve artifact metadata and a fresh signed URL by `artifact_id` |
| `list_artifacts` | List artifacts by `type`, `agent_id`, or `execution_id` |
| `poll_artifact` | **Deprecated** — use the `signed_url` from `create_artifact` or the SQS notification queue instead |

## `create_artifact`

```python
result = await mcp_client.call_tool("create_artifact", {
    "type": "report",                       # ArtifactType — see table below
    "content": report_text,                 # String content to store
    "metadata": {
        "title": "Q3 Summary",
        "generated_by": "analysis-agent",
    },
    "idempotency_key": "task-789-report",   # Optional — prevents duplicate creation
})

artifact_id = result["artifact_id"]
signed_url  = result["signed_url"]          # Pre-signed S3 or CloudFront URL
```

`create_artifact` is **synchronous**: it creates a DynamoDB entry, uploads to S3 with KMS encryption, publishes an SQS notification, and returns `artifact_id` + `signed_url` in a single call. No polling is required.

**Parameter name:** the artifact type field is `"type"`, not `"artifact_type"`.

## `get_artifact`

```python
result = await mcp_client.call_tool("get_artifact", {
    "artifact_id": "art-abc123",
})

print(result["artifact_id"])
print(result["type"])          # e.g. "report"
print(result["signed_url"])    # Fresh pre-signed URL (see TTL below)
print(result["metadata"])
```

**Response field name:** the URL is `"signed_url"`, not `"download_url"`. The URL is generated via `get_best_url()` which selects CloudFront or S3 pre-signed automatically. `list_artifacts` results do not include `signed_url` — call `get_artifact` to obtain a URL for a specific artifact.

## `list_artifacts`

```python
artifacts = await mcp_client.call_tool("list_artifacts", {
    "type": "report",          # Optional — filter by ArtifactType value
    "agent_id": "my-agent",    # Optional — filter by agent
    "execution_id": "exec-1",  # Optional — filter by execution (takes priority over other filters)
    "date": "2024-01-15",      # Optional — filter by date prefix (YYYY-MM-DD)
    "limit": 20,               # Optional — max results (default 50)
})

# Returns a list directly (not wrapped in {"artifacts": [...]})
for item in artifacts:
    print(item["artifact_id"], item["type"], item["created_at"])
```

`list_artifacts` returns a `list[dict]` directly — not a dict with an `"artifacts"` key. There is **no pagination** (`created_after` and `next_token` parameters do not exist). When `execution_id` is provided it takes priority over all other filters. Otherwise, `type`, `agent_id`, and `date` are applied via DynamoDB GSIs on `type+created_at` and `agent_id+created_at`.

## `poll_artifact`

`poll_artifact` is **deprecated**. Use the `signed_url` returned synchronously by `create_artifact`, or subscribe to the `artifact-notifications` SQS queue for event-driven patterns.

## Artifact Types

| `type` value | Typical Use | Extension |
|-------------|-------------|-----------|
| `chart` | Generated visualizations | `.jsx` |
| `report` | Analysis reports | `.md` |
| `simulation_result` | Simulation outputs | `.json` |
| `recommendation` | Agent recommendations | `.json` |
| `image` | Generated or processed images | `.png` |
| `data_export` | Tabular data exports | `.csv` |
| `pipeline_run` | Pipeline execution records | `.json` |

Note: `dataset`, `document`, `audio`, and `raw` are **not** valid artifact types.

## Idempotency

Pass an `idempotency_key` to make creation idempotent. If the same key is submitted again within the artifact's TTL, the existing artifact is returned rather than creating a duplicate:

```python
# Safe to retry — returns the same artifact_id both times
result = await mcp_client.call_tool("create_artifact", {
    "type": "data_export",
    "content": csv_data,
    "idempotency_key": "workflow-run-456-output",
})
```

Essential for Step Functions workflows with retry logic.

## Pre-Signed URL TTL

`get_artifact` generates a fresh signed URL on every call:

| Delivery method | TTL |
|----------------|-----|
| S3 pre-signed URL (default) | 1 hour (`SIGNED_URL_EXPIRY=3600`) |
| CloudFront signed URL (when `CLOUDFRONT_DOMAIN` is set) | 14 days |

CloudFront delivery requires `CLOUDFRONT_DOMAIN`, `CLOUDFRONT_KEY_PAIR_ID`, and `CLOUDFRONT_PRIVATE_KEY_SECRET_ARN` environment variables on the Lambda. The platform injects these when `enable_cloudfront: true` is set in the infrastructure configuration.

## Blueprint Configuration

Declare the artifact Lambda as a Gateway target in the agent blueprint:

```yaml
gateway:
  targets:
    - name: artifacts
      type: lambda
      lambda_arn: "${ARTIFACTS_MCP_LAMBDA_ARN}"
      outbound_auth: GATEWAY_IAM_ROLE
```

`ARTIFACTS_MCP_LAMBDA_ARN` is available as a platform Terraform output (`artifacts_mcp_lambda_arn`) and is injected into agent runtimes automatically when `enable_artifacts_gateway_target: true` is set on the platform module.

## Claim-Check Pattern in Step Functions

```json
{
  "CreateReport": {
    "Type": "Task",
    "Resource": "arn:aws:states:::bedrock-agentcore:invokeAgent",
    "Parameters": {
      "AgentId": "${REPORT_AGENT_ID}",
      "InputText": "Generate the Q3 report and store it as an artifact."
    },
    "ResultPath": "$.artifact",
    "Next": "ProcessReport"
  },
  "ProcessReport": {
    "Type": "Task",
    "Resource": "arn:aws:states:::bedrock-agentcore:invokeAgent",
    "Parameters": {
      "AgentId": "${PROCESSOR_AGENT_ID}",
      "InputText.$": "States.Format('Process artifact: {}', $.artifact.artifact_id)"
    },
    "End": true
  }
}
```

The producing agent stores the report and returns only the `artifact_id`. The consuming agent calls `get_artifact` to retrieve the full payload.

## See Also

- [Tools, MCP & Gateway guide](../tools.md) — Claim-check architecture, Gateway Lambda targets
- [Gateway SDK reference](gateway.md) — Target registration
