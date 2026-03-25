---
title: Artifacts
parent: Concepts
nav_order: 12
---

# Artifact Store

The Artifact Store implements the claim-check pattern for large agent outputs. Instead of passing full data through agent pipelines, agents store artifacts in S3 and pass lightweight references (artifact IDs) through the system. Agents discover artifact tools via MCP through the AgentCore Gateway.

## Why Claim-Check

Agent outputs can be large -- charts, reports, simulation results, data exports. Passing these through Step Functions, agent-to-agent calls, or memory systems creates problems:

- **Step Functions payload limits** -- SFN has a 256 KB payload limit per state
- **Memory bloat** -- storing raw outputs in memory makes retrieval slow and expensive
- **Serialization overhead** -- large objects slow down every inter-agent call

The claim-check pattern solves this: store the artifact in S3, register metadata in DynamoDB, and pass only the artifact ID. Consumers retrieve the full artifact via a signed URL when they actually need it.

## How It Works

```
Agent calls create_artifact(type="report", content="...", tier="domain")
  │
  ├─ 1. DynamoDB catalog entry (status=processing)
  ├─ 2. S3 upload to domain/{artifact_id}/artifact.json (KMS encrypted)
  ├─ 3. DynamoDB status → ready
  ├─ 4. SQS notification → artifact-notifications queue
  └─ 5. Returns {artifact_id, status, s3_key, signed_url}
        │
        ↓
Step Functions passes artifact_id (tiny UUID) between states
        │
        ↓
Next agent calls get_artifact(artifact_id)
  └─ Returns {signed_url, metadata} → agent downloads from S3
```

## Deployment Model

The artifact tools are deployed as a **Lambda function behind the AgentCore Gateway** -- the canonical AgentCore pattern for tools:

```
Agent (Runtime) ── MCP ──> AgentCore Gateway ── IAM ──> Lambda (artifacts-mcp-tools)
                                                          │           │
                                                          ▼           ▼
                                                       S3 bucket   DynamoDB
```

The Gateway auto-exposes the Lambda as MCP tools. Agents discover `create_artifact`, `get_artifact`, `list_artifacts`, and `poll_artifact` through standard MCP tool discovery.

A separate read-only Lambda behind API Gateway REST API serves human/dashboard consumers at `/api/artifacts` and `/api/runs`.

## Storage Architecture

- **S3** stores artifact content at `{tier}/{artifact_id}/artifact.{ext}`, encrypted with tier-specific KMS keys
- **DynamoDB** stores the catalog: artifact ID (partition key), type, status, S3 key, agent ID, execution ID, tier, timestamps, and metadata
- **Three GSIs** enable efficient queries: `type-created_at-index`, `agent_id-created_at-index`, and `execution_id-agent_id-index`
- **SQS** (`artifact-notifications` queue + DLQ) provides event-driven notifications on artifact status changes, enabling downstream consumers to react without polling

## Two-Tier Security Model

Artifacts live in a single S3 bucket with two paths enforced by bucket policy and KMS:

```
s3://{prefix}-{env}-artifacts-{account}/
├── platform/    ← KMS key: platform_artifacts_kms_key
│   └── {artifact_id}/artifact.json
└── domain/      ← KMS key: domain_artifacts_kms_key
    └── {artifact_id}/artifact.json
```

The bucket policy **denies** any `PutObject` to `/platform/*` unless encrypted with the platform KMS key, and any `PutObject` to `/domain/*` unless encrypted with the domain KMS key. Since only platform IAM roles have `kms:GenerateDataKey` on the platform key, and only domain IAM roles have it on the domain key, the bucket policy + KMS grants together create the access boundary.

The `tier` parameter on `create_artifact` (default: `"platform"`) controls which path and KMS key are used. The KMS key is auto-resolved from environment variables (`KMS_KEY_ARN_PLATFORM_ARTIFACTS`, `KMS_KEY_ARN_DOMAIN_ARTIFACTS`) -- callers do not need to specify the key explicitly.

## Artifact Types

| Type | Extension | Use Case |
|------|-----------|----------|
| `chart` | `.json` | Generated visualizations |
| `report` | `.json` | Structured text reports |
| `simulation_result` | `.json` | Simulation engine output |
| `recommendation` | `.json` | Agent recommendations |
| `image` | `.png` | Generated or processed images (base64 encoded) |
| `data_export` | `.csv` | Exported datasets |
| `pipeline_run` | `.json` | Pipeline execution manifests |

## MCP Tools (via AgentCore Gateway)

| Tool | Purpose |
|------|---------|
| `create_artifact` | Store content to S3, register in catalog, publish SQS notification. Returns `artifact_id` and `signed_url` immediately. |
| `get_artifact` | Retrieve metadata and pre-signed download URL |
| `list_artifacts` | List artifacts with type/agent/date/execution filters (uses GSI queries) |
| `poll_artifact` | *(Deprecated)* Wait for artifact readiness. Prefer SQS notifications or use the `signed_url` returned by `create_artifact` directly. |

The `server.py` MCP server (`BaseMCPServer`) also exposes `get_pipeline_run`, `get_latest_run`, `get_agent_result`, and `search_artifacts` for local development. In production, the Gateway Lambda handles the core 4 tools above.

## Signed URLs

Artifact retrieval uses pre-signed URLs rather than direct S3 access. The store supports two URL strategies:

1. **S3 pre-signed URLs** -- default, 1-hour expiry
2. **CloudFront signed URLs** -- when `CLOUDFRONT_DOMAIN` is configured, provides CDN-cached delivery with 14-day expiry and private key signing via Secrets Manager

The `get_best_url()` method automatically picks CloudFront if configured, falling back to S3.

## Event-Driven Notifications

When an artifact's status changes to `ready` or `error`, a message is published to the `artifact-notifications` SQS queue:

```json
{
  "artifact_id": "abc-123",
  "status": "ready",
  "type": "report",
  "agent_id": "analyst",
  "execution_id": "run-42"
}
```

Downstream consumers (Step Functions, other agents) subscribe to this queue instead of polling DynamoDB. The queue has a dead-letter queue with 3-retry redrive and KMS encryption.

If `ARTIFACT_QUEUE_URL` is not set, notifications are silently skipped -- this allows local development without SQS.

## Idempotency

The `create_artifact` tool accepts an optional `idempotency_key`. If a previous artifact with the same key exists, the store returns the existing artifact instead of creating a duplicate. This prevents duplicate artifacts when agent steps are retried.

Recommended format: `{agent_id}:{execution_id}:create_artifact:{param_hash}`

## Package Structure

The `artifacts/` package is a pure Python library consumed by the Lambda handler. It has no server process, no Docker image, and no standalone runtime:

```
artifacts/src/mcp_artifacts/
├── schemas.py          # ArtifactType enum, Pydantic models, helpers
├── storage.py          # S3 put/get, pre-signed URLs, CloudFront
├── catalog.py          # DynamoDB CRUD, GSI queries
├── notifications.py    # SQS status-change publisher
└── tools/
    ├── create.py       # create_artifact — S3 upload + catalog + SQS
    ├── get.py          # get_artifact — catalog lookup + signed URL
    ├── list_artifacts.py  # list with filters
    └── poll.py         # poll (deprecated — use SQS or signed_url from create)
```

The Lambda handler at `core/src/agent_core/api/artifacts_mcp_handler.py` imports these tool functions and dispatches Gateway calls to them.
