# Artifacts Architecture — Forensic Analysis & Decision Record

> **Status:** All findings resolved. Lambda + AgentCore Gateway pattern implemented.
>
> **Date:** 2026-03-24
>
> **Scope:** `artifacts/` package, `core/src/agent_core/mcp/`, deployment model, and integration with AgentCore Gateway.

---

## Resolution Summary (2026-03-25)

All 7 findings from the forensic analysis have been addressed:

| # | Finding | Resolution |
|---|---------|------------|
| F1 | DynamoDB schema mismatch | Fixed: removed `created_at` range key, added 2 missing GSIs |
| F2 | SQS queue unused | Fixed: `notifications.py` publishes to queue on status change |
| F3 | `poll_artifact` busy-loops | Fixed: `create_artifact` returns `signed_url` directly; `poll_artifact` deprecated |
| F4 | `artifacts_api.py` uses scans | Fixed: replaced with GSI queries |
| F5 | No MCP Lambda with write perms | Fixed: added `artifacts-mcp-tools` Lambda + IAM |
| F6 | No Gateway target | Fixed: `artifacts_target.tf` registers 4 tools via Gateway |
| F7 | Fargate assumption | Fixed: Dockerfile marked local-dev-only, uvicorn/starlette moved to `[dev]` |
| F8 | S3 key missing tier prefix — two-tier KMS bypass | Fixed: S3 key now `{tier}/{artifact_id}/{filename}`, KMS key auto-resolved from tier |

**Architecture decision:** Lambda behind AgentCore Gateway (Option 1 from analysis).

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [What Exists Today](#2-what-exists-today)
3. [What the Code Actually Does](#3-what-the-code-actually-does)
4. [The Fargate Question — Forensic Findings](#4-the-fargate-question--forensic-findings)
5. [AgentCore Gateway Can Replace This](#5-agentcore-gateway-can-replace-this)
6. [The Polling Problem — SQS Alternative](#6-the-polling-problem--sqs-alternative)
7. [Architecture Options](#7-architecture-options)
8. [Detailed Comparison Matrix](#8-detailed-comparison-matrix)
9. [Schema Mismatches Found](#9-schema-mismatches-found)
10. [Recommendation](#10-recommendation)
11. [Migration Path](#11-migration-path)

---

## 1. Executive Summary

The `artifacts/` package (`mcp-artifacts`) is a claim-check pattern implementation: large agent outputs go to S3, small UUIDs flow through Step Functions. It exposes 8 MCP tools via a custom HTTP server on Fargate.

**The forensic analysis found:**

- **No Fargate infrastructure exists.** The Dockerfile is there, but `modules/platform/` has zero ECS/Fargate resources. The deployment model was assumed, never built.
- **An SQS queue already exists in Terraform** (`artifact-notifications` + DLQ) but the Python code doesn't use it at all. `poll_artifact` busy-loops DynamoDB instead.
- **The DynamoDB schema in Terraform doesn't match the code.** Terraform defines `created_at` as a range key; the catalog code uses `artifact_id` as PK-only and is missing 2 of the 3 GSIs.
- **Every tool is stateless request/response.** No streaming, no persistent connections, no WebSocket. Even `poll_artifact` is a loop of DynamoDB reads.
- **AgentCore Gateway can auto-expose Lambda functions as MCP tools.** The exact same tool schemas could be served by Lambda behind Gateway — which is the canonical AgentCore pattern for tools.

**Bottom line:** The current design wraps 8 stateless CRUD operations in an MCP HTTP server process. AgentCore Gateway exists precisely to eliminate this pattern — it turns Lambda functions (or OpenAPI specs) into MCP tools natively. The Fargate deployment adds cost, operational complexity, and an infrastructure gap that was never closed.

---

## 2. What Exists Today

### Python Code (`artifacts/src/mcp_artifacts/`)

| File | Purpose | Lines |
|------|---------|-------|
| `server.py` | MCP server entry point, 8 tool registrations via `BaseMCPServer` | ~250 |
| `schemas.py` | `ArtifactType` enum, `ArtifactMeta` Pydantic model, helpers | ~100 |
| `storage.py` | S3 put/get, pre-signed URLs, CloudFront signed URLs | ~110 |
| `catalog.py` | DynamoDB CRUD, GSI queries, idempotency scan | ~180 |
| `tools/create.py` | Create artifact (S3 upload + catalog entry) | ~60 |
| `tools/get.py` | Get artifact (catalog lookup + signed URL) | ~30 |
| `tools/poll.py` | Busy-loop DynamoDB every 2s for up to 60s | ~30 |
| `tools/list_artifacts.py` | Query catalog with filters | ~20 |

### Infrastructure (`modules/platform/modules/data/main.tf`)

| Resource | Status |
|----------|--------|
| DynamoDB `artifacts` table | Exists — **schema mismatch with code** |
| SQS `artifact-notifications` queue | Exists — **completely unused by code** |
| SQS `artifact-notifications-dlq` | Exists — **completely unused by code** |
| S3 `artifacts` bucket | Exists (in `data/` sub-module) |
| CloudFront distribution | Conditional (gated by `cloudfront_enabled`) |
| ECS/Fargate task definition | **Does not exist** |
| ECS/Fargate service | **Does not exist** |
| ECS task role IAM | **Does not exist** |
| ALB/service discovery | **Does not exist** |

### Deployment Artifacts

| File | Status |
|------|--------|
| `Dockerfile` | Exists — builds the MCP server image |
| `docker-compose.yml` | Exists — local dev with LocalStack |
| `pyproject.toml` | Exists — console script `mcp-artifacts` entry point |
| Terraform for deployment | **Missing entirely** |

---

## 3. What the Code Actually Does

### The 8 MCP Tools

| Tool | Operation | Backend | Stateful? | Streaming? | Duration |
|------|-----------|---------|-----------|------------|----------|
| `create_artifact` | S3 PUT + DynamoDB PUT | S3, DDB | No | No | <2s |
| `get_artifact` | DynamoDB GET + presign URL | DDB, S3 | No | No | <200ms |
| `poll_artifact` | DynamoDB GET in loop (2s interval, 60s max) | DDB | **Yes (loop)** | No | 2-60s |
| `list_artifacts` | DynamoDB Query/Scan | DDB | No | No | <500ms |
| `get_pipeline_run` | DynamoDB Query + S3 GET + JSON decode | DDB, S3 | No | No | <1s |
| `get_latest_run` | DynamoDB Query (latest) + S3 GET | DDB, S3 | No | No | <1s |
| `get_agent_result` | DynamoDB Query + S3 GET + auto-decode | DDB, S3 | No | No | <1s |
| `search_artifacts` | DynamoDB Scan + post-filter | DDB | No | No | <1s |

**Key observation:** 7 of 8 tools are pure request/response under 2 seconds. The one exception (`poll_artifact`) is a workaround for not using event-driven notifications.

### What `BaseMCPServer` Adds

The `BaseMCPServer` class from `core/src/agent_core/mcp/base_server.py` provides:

1. Tool registration decorators
2. Transport abstraction (stdio/HTTP/SSE)
3. Error wrapping
4. Health endpoint
5. Observability hooks

**However:** AgentCore Gateway provides all of this natively for Lambda targets. The Gateway auto-generates MCP tool schemas, handles auth, routes calls, and returns structured responses — the same contract `BaseMCPServer` implements manually.

---

## 4. The Fargate Question — Forensic Findings

### Why Fargate Was Assumed

The `Dockerfile`, `docker-compose.yml`, and `MCP_TRANSPORT=http` configuration all point toward a long-running container deployment. The `BaseMCPServer` HTTP transport binds to `0.0.0.0:8004` — a Fargate-style pattern.

### Why Fargate Was Never Built

There are zero ECS resources in `modules/platform/`. No task definitions, no services, no ALBs, no service discovery, no task roles. The Terraform modules focus entirely on:

- AgentCore Runtime (for agents)
- AgentCore Gateway (for tool routing)
- DynamoDB, S3, SQS (data layer)
- KMS, IAM, VPC (security)

The deployment gap was never closed because the infrastructure team focused on AgentCore-native resources, not custom compute.

### Why Fargate is Wrong for This Workload

| Factor | Analysis |
|--------|----------|
| **Cost** | Fargate runs 24/7 whether tools are called or not. Artifacts tools are called during pipeline runs (minutes/day), not continuously. Lambda pays only per invocation. |
| **Scaling** | Fargate needs explicit scaling policies. Lambda scales to zero and handles burst automatically. |
| **Operational overhead** | Fargate needs: task definition, service, ALB or Cloud Map, health checks, container image lifecycle, ECR, task role, security groups, log group. Lambda needs: function + IAM role. |
| **Cold starts** | Not a concern — artifact operations are not latency-sensitive. A 500ms Lambda cold start is fine for storing a report. |
| **Persistent connections** | Not needed — every tool is request/response. Even `poll_artifact` could be replaced by SQS. |
| **State** | The code is stateless. No in-memory state, no connection pools (boto3 creates clients per-call), no sessions. The Redis cache in `BaseMCPServer` is optional and unused by artifacts. |
| **Auth** | Fargate needs custom auth. AgentCore Gateway provides IAM + JWT auth natively for all targets. |

---

## 5. AgentCore Gateway Can Replace This

### How Gateway Auto-Converts Tools to MCP

From the AgentCore documentation and samples:

```
Agent ──── MCP ────> Gateway ──── IAM Role ────> Lambda fn
```

The Gateway accepts three target types relevant here:

#### Option A: Lambda Target with Inline Tool Schema

```python
# Gateway target definition — replaces the entire MCP server
create_gateway_target(
    gatewayIdentifier=gateway_id,
    name="ArtifactTools",
    targetConfiguration={
        "mcp": {
            "lambda": {
                "lambdaArn": artifacts_lambda_arn,
                "toolSchema": {
                    "inlinePayload": [
                        {
                            "name": "create_artifact",
                            "description": "Store agent output as S3 artifact",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string"},
                                    "content": {"type": "string"},
                                    "agent_id": {"type": "string"},
                                    "execution_id": {"type": "string"}
                                },
                                "required": ["type", "content"]
                            }
                        },
                        # ... 6 more tools
                    ]
                }
            }
        }
    },
    credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}]
)
```

The agent calls `create_artifact(type="report", content="...")` via MCP. Gateway routes to Lambda. Lambda does S3 + DynamoDB. Response flows back. **Identical behavior, zero custom infrastructure.**

#### Option B: OpenAPI Spec on S3

We could also write an OpenAPI/Swagger spec for the artifact operations and upload it to S3. Gateway auto-generates MCP tools from each endpoint:

```yaml
# artifacts-openapi.yaml → uploaded to S3
paths:
  /artifacts:
    post:
      operationId: create_artifact
      summary: Store agent output as S3 artifact
      # ... schema
    get:
      operationId: list_artifacts
      summary: List artifacts with filters
  /artifacts/{artifact_id}:
    get:
      operationId: get_artifact
      summary: Get artifact metadata and signed URL
```

Gateway reads this spec and exposes each operation as an MCP tool. The backend can be Lambda or any HTTP endpoint.

#### Option C: MCP Server on AgentCore Runtime

If we truly needed a persistent MCP server, the correct deployment target is **AgentCore Runtime with `server_protocol: MCP`**, not Fargate. This is what the `mcp_runtime_targets` in `gateway_targets.tf` already supports:

```hcl
# Already in our codebase — agents/gateway_targets.tf
resource "aws_bedrockagentcore_gateway_target" "mcp_runtime" {
  for_each = local.mcp_runtime_targets  # blueprints with protocol: MCP

  target_configuration {
    mcp {
      mcp_server {
        endpoint = "https://bedrock-agentcore.../runtimes/${runtime_arn}/invocations"
      }
    }
  }
}
```

But this is overkill for artifacts — Runtime is designed for stateful agents, not CRUD tool servers.

---

## 6. The Polling Problem — SQS Alternative

### Current: `poll_artifact` Busy-Loops DynamoDB

```python
# tools/poll.py — current implementation
async def poll_artifact(artifact_id, timeout_s=60):
    for _ in range(timeout_s // 2):
        entry = catalog.get_entry(artifact_id)
        if entry["status"] in ("ready", "error", "not_found"):
            return entry
        await asyncio.sleep(2)  # Busy loop!
    return {"status": "timeout"}
```

**Problems:**
- Wastes DynamoDB read capacity (up to 30 reads per poll)
- Blocks the calling agent for up to 60 seconds
- Requires a long-running process to hold the loop
- Not event-driven

### The SQS Queue Already Exists

Terraform already provisions:

```hcl
# modules/platform/modules/data/main.tf
resource "aws_sqs_queue" "artifact_notifications" {
  name                       = "${var.resource_prefix}-${var.environment}-artifact-notifications"
  visibility_timeout_seconds = 300
  # KMS encrypted, DLQ with 3 retries
}
```

**But the Python code never publishes to it or consumes from it.**

### Better Pattern: Event-Driven Notifications

```
create_artifact()
  ├─ S3 PUT
  ├─ DynamoDB PUT (status=processing)
  ├─ ... processing ...
  ├─ DynamoDB UPDATE (status=ready)
  └─ SQS SendMessage({artifact_id, status: "ready"})  ← NEW

# Downstream: Step Functions or agent polls SQS instead of DynamoDB
# Or: DynamoDB Streams → Lambda → SQS (fully event-driven)
# Or: S3 Event Notification → SQS (fires when upload completes)
```

**With SQS, `poll_artifact` is eliminated entirely.** The consuming agent (or Step Functions) receives an SQS message when the artifact is ready. No busy-looping. No long-lived process needed.

### Even Simpler: Synchronous Create

For most artifact types, `create_artifact` completes in under 2 seconds. The `processing → ready` lifecycle is unnecessary when the S3 upload is synchronous. The tool could return the signed URL immediately:

```python
async def create_artifact(type, content, ...):
    artifact_id = uuid4()
    s3_key = f"{artifact_id}/artifact.{ext}"
    storage.put_object(s3_key, encode(content), content_type)  # Synchronous
    catalog.create_entry(artifact_id, ..., status="ready")     # Already ready
    return {"artifact_id": artifact_id, "signed_url": storage.generate_signed_url(s3_key)}
```

**No need to poll at all.** The two-phase lifecycle (`processing → ready`) only makes sense for async processing (e.g., image conversion, report generation). For direct S3 uploads, it's unnecessary overhead.

---

## 7. Architecture Options

### Option 1: Lambda Behind AgentCore Gateway (Recommended)

```
┌─────────────┐     MCP      ┌──────────────────┐     IAM      ┌──────────────────┐
│    Agent     │────────────>│  AgentCore        │────────────>│  Lambda           │
│  (Runtime)   │              │  Gateway          │              │  artifacts-fn     │
│              │<────────────│  (auto MCP)       │<────────────│                   │
└─────────────┘              └──────────────────┘              └──────────────────┘
                                                                  │         │
                                                                  ▼         ▼
                                                               S3 bucket  DynamoDB
```

**What changes:**
- `artifacts/` Python code → single Lambda function (same logic, different entry point)
- Tool schemas → Gateway target inline payload (Terraform)
- `BaseMCPServer` → removed (Gateway handles MCP protocol)
- `Dockerfile` → removed (Lambda deployment)
- `poll_artifact` → SQS notification or synchronous create

**What stays:**
- `storage.py`, `catalog.py`, `schemas.py` — reused in Lambda
- S3 bucket, DynamoDB table, KMS — already in Terraform
- Claim-check pattern — unchanged

### Option 2: Fargate (Complete the Gap)

```
┌─────────────┐     MCP/HTTP    ┌──────────────────┐
│    Agent     │───────────────>│  Fargate          │
│  (Runtime)   │                │  mcp-artifacts    │
│              │<───────────────│  (8004/tcp)       │
└─────────────┘                └──────────────────┘
                                  │         │
                                  ▼         ▼
                               S3 bucket  DynamoDB
```

**What's needed:**
- ECS cluster, task definition, service, task role
- ALB or Cloud Map for service discovery
- Security groups, health checks
- ECR repository, image lifecycle
- Auto-scaling policy
- ~150 lines of new Terraform

### Option 3: AgentCore Runtime as MCP Server

```
┌─────────────┐     MCP      ┌──────────────────┐     MCP      ┌──────────────────┐
│    Agent     │────────────>│  AgentCore        │────────────>│  AgentCore        │
│  (Runtime)   │              │  Gateway          │              │  Runtime          │
│              │<────────────│                    │<────────────│  mcp-artifacts    │
└─────────────┘              └──────────────────┘              │  (protocol: MCP)  │
                                                               └──────────────────┘
```

**What's needed:**
- Blueprint YAML with `runtime.protocol: MCP`
- `gateway_targets.tf` already handles auto-registration
- OAuth2 credential provider for Gateway → Runtime auth
- More expensive per-session than Lambda

### Option 4: Direct SDK Integration (No Server)

```
┌─────────────┐
│    Agent     │──── import agent_core.artifacts ────> S3 + DynamoDB directly
│  (Runtime)   │
└─────────────┘
```

**What changes:**
- Artifact operations become a library, not a service
- Each agent imports and calls directly — no network hop
- Simplest possible architecture
- Loses tool discoverability (agents can't "discover" artifact tools via MCP)

---

## 8. Detailed Comparison Matrix

| Criterion | Lambda + Gateway | Fargate | Runtime MCP | Direct SDK |
|-----------|:----------------:|:-------:|:-----------:|:----------:|
| **Cost (idle)** | $0 | ~$35/mo (0.25 vCPU) | ~$0 (no sessions) | $0 |
| **Cost (active)** | ~$0.01/1K calls | Same as idle | Per-session-second | $0 |
| **Scale to zero** | Yes | No | Yes | N/A |
| **Auto-scaling** | Automatic | Manual policy | Automatic | N/A |
| **Cold start** | 500ms-2s | None | ~1s | None |
| **MCP native** | Via Gateway | Custom server | Via Gateway | No |
| **Tool discovery** | Gateway auto | Custom | Gateway auto | No |
| **Auth** | Gateway IAM/JWT | Custom | Gateway OAuth2 | Agent IAM |
| **Infra complexity** | Low (Lambda + target) | High (~150 LOC TF) | Medium (blueprint) | None |
| **Operational burden** | Low (managed) | High (containers) | Low (managed) | None |
| **Streaming support** | No | Yes | Yes | N/A |
| **Persistent state** | No | Yes | Yes (per-session) | No |
| **Existing TF ready** | Partial (Gateway exists) | Nothing | Partial (targets exist) | S3+DDB exist |
| **Fits AgentCore model** | Canonical pattern | Off-pattern | Valid but heavy | Off-pattern |
| **Polling elimination** | SQS or sync | Still needs polling | Still needs polling | SQS or sync |

---

## 9. Schema Mismatches Found

### DynamoDB Table: Code vs. Terraform

| Aspect | Python Code (`catalog.py`) | Terraform (`data/main.tf`) |
|--------|---------------------------|---------------------------|
| **Primary key** | `artifact_id` (HASH only) | `artifact_id` (HASH) + `created_at` (RANGE) |
| **GSI 1** | `type-created_at-index` | `agent_id-created_at-index` |
| **GSI 2** | `agent_id-created_at-index` | *(only 1 GSI defined)* |
| **GSI 3** | `execution_id-agent_id-index` | *(missing)* |

**Impact:** The code will fail at runtime because:
1. `catalog.get_entry(artifact_id)` sends `Key={"artifact_id": id}` — but the table has a composite key requiring both `artifact_id` AND `created_at`
2. Queries against `type-created_at-index` and `execution_id-agent_id-index` will fail — those GSIs don't exist in Terraform

**Fix required regardless of deployment model.**

### SQS Queue: Provisioned but Unused

The `artifact-notifications` queue and its DLQ exist in Terraform with:
- KMS encryption
- 300s visibility timeout
- 3-retry DLQ redrive

But zero lines of Python code reference SQS. The queue was designed to support event-driven artifact notifications but was never wired up.

---

## 10. Recommendation

### Primary: Option 1 — Lambda Behind AgentCore Gateway

**Rationale:**

1. **It's the canonical AgentCore pattern.** The CONCEPTS.md from the official samples is explicit: *"agents live on Runtime, tools live on Lambda, Gateway bridges them."* Every sample follows this. Fargate is never used for tools.

2. **Gateway handles MCP natively.** The inline tool schema in `create_gateway_target` eliminates `BaseMCPServer`, the Dockerfile, the HTTP transport, and all MCP protocol handling. Gateway auto-generates the MCP interface.

3. **Zero operational overhead.** Lambda + Gateway is fully managed. No container images, no ECR lifecycle, no health checks, no scaling policies, no ALB.

4. **Cost efficiency.** Artifacts are created during pipeline runs — maybe hundreds/day, not thousands/second. Lambda costs effectively $0 at this scale vs. ~$35/mo minimum for Fargate.

5. **SQS replaces polling.** Wire `create_artifact` to publish to the existing SQS queue on status change. Downstream consumers (Step Functions, agents) subscribe to SQS instead of busy-looping DynamoDB.

6. **The infrastructure is half-built.** Gateway already exists in Terraform. The S3 bucket, DynamoDB table, SQS queues, and KMS keys already exist. Only a Lambda function and a Gateway target definition are missing.

### When to Use Other Options

| Scenario | Recommended Option |
|----------|--------------------|
| Standard artifact CRUD (current scope) | **Option 1: Lambda + Gateway** |
| Streaming large file uploads (future) | Option 3: Runtime MCP |
| Real-time artifact processing pipeline | Option 3: Runtime MCP + SQS |
| Agent needs artifacts without MCP discovery | Option 4: Direct SDK |

---

## 11. Migration Path

### Phase 1: Fix Schema Mismatches (Do Now)

1. Align DynamoDB table definition in Terraform with code expectations:
   - Remove `created_at` as range key (or update code to include it in all operations)
   - Add missing GSIs: `type-created_at-index`, `execution_id-agent_id-index`
2. Wire `create_artifact` to publish SQS notification on status change
3. Replace `poll_artifact` with SQS-based notification or make `create_artifact` synchronous

### Phase 2: Lambda Function (Replace Fargate)

1. Create `artifacts/lambda_handler.py` — single Lambda entry point routing tool calls
2. Reuse `storage.py`, `catalog.py`, `schemas.py`, tool functions — they're already stateless
3. Add Lambda resource to `modules/platform/` (or a new `modules/artifacts/` sub-module)
4. Add Gateway target in `modules/agents/gateway_targets.tf` (or platform-level gateway)

### Phase 3: Deprecate MCP Server

1. Remove `BaseMCPServer` dependency from `artifacts/`
2. Remove `Dockerfile`, `docker-compose.yml`
3. Keep `artifacts/` as a Python package (Lambda handler + shared logic)
4. Update `pyproject.toml` to remove `mcp[server]`, `uvicorn`, `starlette` dependencies

### What Stays Unchanged

- `core/src/agent_core/mcp/` — Still used by domain MCP servers that genuinely need persistent processes
- `BaseMCPServer` — Still the base class for domain MCPs (market data feeds, browser tools, etc.)
- Claim-check pattern — Unchanged. S3 for content, UUIDs through Step Functions
- `schemas.py`, `storage.py`, `catalog.py` — Reused inside Lambda

---

## Appendix: AgentCore Gateway Target Types

From the official AgentCore samples and CONCEPTS:

| Target Type | Backend | Auth | Use Case |
|-------------|---------|------|----------|
| **Lambda** | Lambda function ARN | `GATEWAY_IAM_ROLE` | Short, stateless tools (CRUD, lookups, transforms) |
| **OpenAPI** | Any HTTP API (spec on S3) | OAuth2 or IAM | REST APIs auto-converted to MCP tools |
| **MCP Server** | AgentCore Runtime (`protocol: MCP`) | OAuth2 credential provider | Persistent tool servers (stateful, streaming) |
| **Smithy** | Smithy API endpoint | Various | AWS-style service APIs |
| **API Gateway** | AWS API Gateway endpoint | Various | Existing API Gateway deployments |

**The artifacts workload maps to Lambda target.** It's stateless, fast, and doesn't need persistent connections. The canonical AgentCore pattern for tools.
