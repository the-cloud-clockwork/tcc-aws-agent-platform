---
title: Artifacts Server
nav_order: 12
---

# Artifacts Server

The Artifacts Server is a standalone MCP server (`mcp-artifacts`) that implements the claim-check pattern for large agent outputs. Instead of passing large payloads through Step Functions or agent-to-agent calls, agents store outputs in S3 and pass lightweight artifact keys. Downstream consumers retrieve the full payload via pre-signed URL.

## The Claim-Check Pattern

Step Functions and A2A messages have payload size limits. Large outputs (reports, datasets, generated files) must not be inlined. The claim-check pattern solves this:

1. Agent produces a large output
2. Agent calls `create_artifact` → gets back an `artifact_id`
3. Agent passes the `artifact_id` (small key) through Step Functions / A2A
4. Downstream agent calls `get_artifact(artifact_id)` to retrieve the full payload
5. Payload is served via a time-limited pre-signed S3 URL

The artifacts server is the MCP server that implements steps 2 and 4.

## MCP Tools

The server exposes four MCP tools:

### create_artifact

Store a new artifact and get back its ID:

```python
# Called by the Strands agent via MCP
result = await mcp_client.call_tool("create_artifact", {
    "artifact_type": "report",
    "content": report_bytes,          # or "content_s3_uri" for pre-uploaded content
    "content_type": "application/pdf",
    "metadata": {
        "title": "Q3 Summary",
        "generated_by": "analysis-agent",
    },
    "idempotency_key": "task-789-report",   # Optional: prevents duplicate creation
    "ttl_hours": 48,                        # Optional: default from server config
})

artifact_id = result["artifact_id"]
```

### get_artifact

Retrieve an artifact by ID:

```python
result = await mcp_client.call_tool("get_artifact", {
    "artifact_id": "art-abc123",
})

print(result["artifact_type"])      # "report"
print(result["content_type"])       # "application/pdf"
print(result["download_url"])       # Pre-signed S3 URL (15-minute TTL)
print(result["metadata"])
print(result["size_bytes"])
```

The `download_url` is a pre-signed S3 URL valid for a short window. The recipient downloads the content directly from S3, not through the artifacts server.

### list_artifacts

List artifacts matching a filter:

```python
result = await mcp_client.call_tool("list_artifacts", {
    "artifact_type": "report",
    "created_after": "2024-01-01T00:00:00Z",
    "limit": 20,
    "next_token": result.get("next_token"),   # Pagination
})

for item in result["artifacts"]:
    print(item["artifact_id"], item["artifact_type"], item["created_at"])
```

### poll_artifact

Poll for an artifact that may not yet exist (for async workflows):

```python
result = await mcp_client.call_tool("poll_artifact", {
    "artifact_id": "art-abc123",
    "timeout_seconds": 30,
    "poll_interval_seconds": 2,
})

if result["status"] == "ready":
    print(result["download_url"])
elif result["status"] == "timeout":
    # Artifact not ready within the timeout window
    pass
```

Use `poll_artifact` when a workflow produces an artifact asynchronously and the consumer needs to wait for it.

## Artifact Types

| Type | Use Case | Typical Content-Type |
|------|----------|---------------------|
| `report` | Generated reports or analysis outputs | `application/pdf`, `text/html` |
| `dataset` | Tabular or structured data outputs | `text/csv`, `application/json` |
| `document` | Generated documents or drafts | `application/pdf`, `text/markdown` |
| `image` | Generated or processed images | `image/png`, `image/jpeg` |
| `audio` | Generated audio files | `audio/mpeg`, `audio/wav` |
| `raw` | Arbitrary binary payloads | Any `content_type` |

## Idempotency

Pass an `idempotency_key` to `create_artifact` to make creation idempotent. If the same key is submitted twice within the key's TTL, the server returns the existing artifact ID rather than creating a duplicate:

```python
# Safe to retry — returns the same artifact_id both times
result = await mcp_client.call_tool("create_artifact", {
    "artifact_type": "dataset",
    "content": data,
    "idempotency_key": "workflow-run-456-output",
})
```

This is essential for Step Functions workflows with retry logic, where a task may execute more than once.

## Pre-Signed URLs

`get_artifact` returns a pre-signed S3 URL rather than the content bytes. This design:

- Keeps the MCP server stateless and horizontally scalable
- Allows large files without streaming through the server process
- Lets the pre-sign TTL act as a lightweight expiry for sensitive content
- Works naturally with browser-based consumers that can follow redirects

The pre-sign TTL defaults to 15 minutes and is configurable per-call via `url_expiry_seconds`.

## Step Functions Integration

The canonical Step Functions integration pattern:

```json
{
  "CreateArtifact": {
    "Type": "Task",
    "Resource": "arn:aws:states:::bedrock-agentcore:invokeAgent",
    "Parameters": {
      "AgentId": "${ARTIFACT_AGENT_ID}",
      "InputText": "Store this report as an artifact",
      "SessionAttributes": {
        "report_content.$": "$.report"
      }
    },
    "ResultPath": "$.artifact",
    "Next": "ProcessArtifact"
  }
}
```

The agent stores the report via `create_artifact` and returns only the `artifact_id` in its response. Step Functions passes the small key to the next state.

## Blueprint Configuration

```yaml
# agent.yaml — declare the artifacts server as a Gateway target
gateway:
  targets:
    - id: artifacts
      type: MCP
      endpoint: "${ARTIFACTS_MCP_ENDPOINT}"
      auth:
        type: api_key
        secret_arn: "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:artifacts-api-key"
```

The artifacts server itself is configured via its own server config (managed by platform infrastructure), not the agent blueprint.
