---
title: Artifacts
nav_order: 4
parent: "Tools, MCP & Gateway"
---

# Artifact Store

The Artifact Store implements the claim-check pattern for large agent outputs. Instead of passing full data through agent pipelines, agents store artifacts in S3 and pass lightweight references (artifact IDs). Consumers retrieve the full artifact via a signed URL when they actually need it. Agents discover and invoke artifact tools via MCP through the AgentCore Gateway.

## Why Claim-Check

Agent outputs can be large — charts, reports, simulation results, data exports. Passing these payloads through Step Functions, agent-to-agent calls, or memory systems creates problems:

- **Step Functions payload limits** — SFN enforces a 256 KB limit per state transition
- **Memory bloat** — storing raw outputs in memory makes retrieval slow and expensive
- **Serialization overhead** — large objects slow down every inter-agent call

The claim-check pattern solves this: store the artifact in S3, register metadata in DynamoDB, and pass only the artifact ID through the pipeline. Consumers retrieve the full artifact via a signed URL when they actually need it.

## How It Works

```
Agent calls create_artifact(type="report", content="...", tier="domain")
  │
  ├─ 1. DynamoDB catalog entry created (status=processing)
  ├─ 2. Content uploaded to S3 (KMS encrypted, tier-specific key)
  ├─ 3. DynamoDB status updated to ready
  ├─ 4. SQS notification published to artifact-notifications queue
  └─ 5. Returns {artifact_id, status, s3_key, signed_url} immediately
        │
        ↓
Step Functions passes artifact_id (small UUID string) between states
        │
        ↓
Next agent calls get_artifact(artifact_id)
  └─ Returns {signed_url, metadata} → agent downloads content from S3
```

`create_artifact` is **synchronous** — it completes the full upload pipeline and returns `status=ready` plus a `signed_url` in one call. No polling is required.

## Deployment Model

The artifact tools run as a **Lambda function registered as an AgentCore Gateway Lambda target**. Agents access the tools through the Gateway via standard MCP tool discovery:

```
Agent (Runtime) ── MCP ──> AgentCore Gateway ── IAM SigV4 ──> Lambda (artifacts-mcp-tools)
                                                                    │              │
                                                                    ▼              ▼
                                                                 S3 bucket    DynamoDB
```

The `artifacts/` package is a pure Python library. It has no standalone server process or Docker image. The Lambda handler at `core/src/agent_core/api/artifacts_mcp_handler.py` imports the tool functions and dispatches Gateway calls to them.

## The Four MCP Tools

| Tool | Purpose |
|------|---------|
| `create_artifact` | Upload content to S3, register in DynamoDB catalog, publish SQS notification. Returns `artifact_id` and `signed_url` immediately. |
| `get_artifact` | Retrieve catalog metadata and a fresh pre-signed download URL for an artifact. |
| `list_artifacts` | List artifacts with optional filters by type, agent ID, execution ID, or date. Uses DynamoDB GSIs for efficient queries. |
| `poll_artifact` | *(Deprecated)* Wait for artifact readiness. `create_artifact` is now synchronous — use the `signed_url` it returns or subscribe to the SQS `artifact-notifications` queue instead. |

## Artifact Types

| Type | File format | Content type |
|------|------------|-------------|
| `chart` | `.jsx` | `text/jsx` |
| `report` | `.md` | `text/markdown` |
| `simulation_result` | `.json` | `application/json` |
| `recommendation` | `.json` | `application/json` |
| `image` | `.png` | `image/png` (content must be base64-encoded) |
| `data_export` | `.csv` | `text/csv` |
| `pipeline_run` | `.json` | `application/json` |

The `type` parameter on `create_artifact` must be one of these exact values.

## Tool Parameters

### create_artifact

```python
create_artifact(
    type="report",                           # Required: ArtifactType value
    content="# Analysis\n\nFindings...",     # Required: raw string (base64 for image)
    metadata={"title": "Q3 Summary"},        # Optional: arbitrary key/value dict
    agent_id="analysis-agent",              # Optional: agent that produced this
    execution_id="run-abc-123",             # Optional: pipeline run identifier
    idempotency_key="run-abc-123:report",   # Optional: prevents duplicate creation
    tier="domain",                          # Optional: "platform" (default) or "domain"
)
# Returns: {artifact_id, status, s3_key, signed_url}
```

### get_artifact

```python
get_artifact(artifact_id="abc-123-def-456")
# Returns: {artifact_id, status, signed_url, type, metadata}
```

### list_artifacts

```python
list_artifacts(
    artifact_type="report",                 # Optional filter by type
    agent_id="analysis-agent",             # Optional filter by agent
    execution_id="run-abc-123",            # Optional filter by execution
)
# Returns: list of catalog entries matching the filters
# Uses DynamoDB GSIs: type-created_at-index, agent_id-created_at-index,
#                     execution_id-agent_id-index
```

## Storage Architecture

- **S3** stores artifact content at `{tier}/{artifact_id}/artifact.{ext}`, encrypted with tier-specific KMS keys
- **DynamoDB** stores the catalog with three GSIs for efficient queries:
  - `type-created_at-index` — list all artifacts of a given type sorted by creation time
  - `agent_id-created_at-index` — list all artifacts from a given agent
  - `execution_id-agent_id-index` — list all artifacts from a specific pipeline run
- **SQS** (`artifact-notifications` queue + DLQ) provides event-driven status notifications

## Two-Tier Security Model

Artifacts live in a single S3 bucket with two tier paths, each protected by its own KMS key:

```
s3://{prefix}-{env}-artifacts-{account}/
├── platform/    ← KMS key: platform_artifacts_kms_key
│   └── {artifact_id}/artifact.{ext}
└── domain/      ← KMS key: domain_artifacts_kms_key
    └── {artifact_id}/artifact.{ext}
```

The bucket policy denies any write to `platform/*` unless encrypted with the platform KMS key, and any write to `domain/*` unless encrypted with the domain KMS key. IAM grants for `kms:GenerateDataKey` enforce the boundary: only platform roles can write platform artifacts, only domain roles can write domain artifacts.

The `tier` parameter on `create_artifact` defaults to `"platform"`. The KMS key is auto-resolved from environment variables (`KMS_KEY_ARN_PLATFORM_ARTIFACTS`, `KMS_KEY_ARN_DOMAIN_ARTIFACTS`) — callers never specify keys explicitly.

## Signed URLs

Artifact retrieval uses pre-signed URLs rather than direct S3 access. The store supports two URL strategies via `get_best_url()`:

1. **S3 pre-signed URLs** — default, 1-hour expiry (`SIGNED_URL_EXPIRY` env var, default 3600 seconds)
2. **CloudFront signed URLs** — when `CLOUDFRONT_DOMAIN` is set, provides CDN-cached delivery with 14-day expiry. Requires `CLOUDFRONT_DOMAIN`, `CLOUDFRONT_KEY_PAIR_ID`, and `CLOUDFRONT_PRIVATE_KEY_SECRET_ARN` (Secrets Manager secret containing the RSA private key)

`get_best_url()` automatically prefers CloudFront when configured and falls back to S3.

## Idempotency

`create_artifact` accepts an optional `idempotency_key`. If a catalog entry with that key already exists, the tool returns the existing artifact without re-uploading. This prevents duplicate artifacts when agent steps are retried by Step Functions:

```python
create_artifact(
    type="report",
    content=report_text,
    idempotency_key="pipeline-run-456:analysis-agent:final-report",
)
# Safe to call multiple times — returns the same artifact_id on retries
```

Recommended format: `{agent_id}:{execution_id}:{step_name}:{param_hash}`

## Event-Driven Notifications

When an artifact transitions to `ready` or `error`, a message is published to the `artifact-notifications` SQS queue:

```json
{
  "artifact_id": "abc-123",
  "status": "ready",
  "type": "report",
  "agent_id": "analysis-agent",
  "execution_id": "run-456"
}
```

Downstream consumers (Step Functions, other agents, dashboards) subscribe to this queue instead of polling DynamoDB. The queue has a DLQ with 3-retry redrive and KMS encryption.

If `ARTIFACT_QUEUE_URL` is not set, notifications are silently skipped — this allows the artifact package to work in local development without SQS configured.

## Package Structure

```
artifacts/src/mcp_artifacts/
├── schemas.py          # ArtifactType enum, Pydantic models, content-type map
├── storage.py          # S3 put/get, pre-signed URLs, CloudFront
├── catalog.py          # DynamoDB CRUD and GSI queries
├── notifications.py    # SQS status-change publisher
└── tools/
    ├── create.py       # create_artifact — full upload pipeline
    ├── get.py          # get_artifact — catalog lookup + signed URL
    ├── list_artifacts.py  # list with type/agent/execution filters
    └── poll.py         # poll_artifact (deprecated)
```

The Lambda handler at `core/src/agent_core/api/artifacts_mcp_handler.py` imports these tool functions and dispatches incoming Gateway calls to them. It supports two invocation formats: the standard Gateway format (`{"name": "create_artifact", "arguments": {...}}`) and a direct invocation format where the arguments are the top-level event dict.

## See Also

- [Gateway](gateway) — the AgentCore Gateway that fronts the artifact Lambda
- [Artifacts SDK Reference](../sdk/artifacts) — tool parameter reference and response schemas
- [Infrastructure: Agents Module](../infrastructure/agents-module) — how the artifacts Lambda target is provisioned
