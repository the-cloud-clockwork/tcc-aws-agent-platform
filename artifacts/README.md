# mcp-artifacts

> Artifact store library — claim-check pattern for agent outputs (S3 + DynamoDB)

Python library implementing the claim-check pattern for agent outputs. Agents store large results (charts, reports, simulation results, data exports) in S3 and pass lightweight artifact IDs through Step Functions pipelines.

## Deployment

Deployed as a **Lambda function behind AgentCore Gateway**. Agents discover artifact tools via MCP through the Gateway. No standalone server process.

```
Agent (Runtime) ── MCP ──> AgentCore Gateway ── IAM ──> Lambda (artifacts-mcp-tools)
                                                          │           │
                                                          ▼           ▼
                                                       S3 bucket   DynamoDB
```

## Features

- **4 MCP tools** — `create_artifact`, `get_artifact`, `list_artifacts`, `poll_artifact` (deprecated)
- **7 artifact types** — chart, report, simulation_result, recommendation, image, data_export, pipeline_run
- **Two-tier security** — `/platform/*` and `/domain/*` S3 paths with separate KMS keys enforced by bucket policy
- **Pre-signed URLs** — returned immediately on `create_artifact`, 1-hour expiry
- **SQS notifications** — status-change events published to `artifact-notifications` queue
- **Idempotency** — `idempotency_key` prevents duplicate writes on agent retries
- **GSI queries** — efficient lookups by type, agent_id, execution_id
- **Dependency injection** — all tools accept injected `storage`/`catalog` for testing

## Package Structure

```
src/mcp_artifacts/
├── schemas.py          # ArtifactType enum, Pydantic models, helpers
├── storage.py          # S3 put/get, pre-signed URLs, CloudFront
├── catalog.py          # DynamoDB CRUD, GSI queries
├── notifications.py    # SQS status-change publisher
└── tools/
    ├── create.py       # S3 upload + catalog + SQS notification + signed URL
    ├── get.py          # Catalog lookup + signed URL
    ├── list_artifacts.py  # Query with filters
    └── poll.py         # Deprecated — use SQS or signed_url from create
```

## Lambda Handler

The Lambda handler at `core/src/agent_core/api/artifacts_mcp_handler.py` imports these tool functions and dispatches AgentCore Gateway calls.

## Terraform

Infrastructure is in `modules/platform/`:
- `modules/api/main.tf` — Lambda function + IAM role
- `modules/agentcore/artifacts_target.tf` — Gateway target registration
- `modules/data/main.tf` — DynamoDB table + SQS queues
- `modules/data/s3.tf` — S3 bucket with two-tier KMS bucket policy
