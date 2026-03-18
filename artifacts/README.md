# mcp-artifacts

> Artifacts MCP Server — universal output pipeline for all agents

MCP server that serves as the universal output bus for all platform agents. Every agent output (charts, reports, simulation results, recommendations, images, data exports) is stored to S3 via this server and retrieved by a small artifact ID — implementing the claim-check pattern required by AWS Step Functions' 256 KB payload limit.

## Architecture Role

```
INTERACTION    →  Claude.ai / Custom UI
     ↕
MCP SKILLS     →  artifacts-mcp  ← THIS REPO (port 8004)
     ↕
AGENTS         →  All agents store outputs here (claim-check pattern)
     ↕
ORCHESTRATION  →  Step Functions passes S3 keys (not payloads)
     ↕
EXECUTION CONTROL →  External Executor
```

## Features

- **4 MCP tools** — create, get, poll, and list artifacts
- **6 artifact types** — chart (JSX), report (Markdown), simulation_result (JSON), recommendation (JSON), image (PNG), data_export (CSV)
- **Dual storage** — S3 for content, DynamoDB for metadata and catalog
- **Pre-signed URLs** — 1-hour GET URLs generated on retrieval, never stored
- **Idempotency** — `idempotency_key` parameter on `create_artifact` prevents duplicate writes on agent retries
- **Async polling** — `poll_artifact` loops every 2 s until ready, error, or timeout
- **DynamoDB GSIs** — efficient queries by artifact type and agent ID without full table scans
- **Dependency injection** — all tools accept injected `storage`/`catalog` instances, enabling fully mocked unit tests via `moto`

## Tool Catalog

| Tool | Description | Key Inputs | Output |
|---|---|---|---|
| `create_artifact` | Upload content to S3 and register in DynamoDB catalog | `type`, `content`, `metadata`, `agent_id`, `execution_id`, `idempotency_key` | `artifact_id`, `status`, `s3_key` |
| `get_artifact` | Retrieve artifact metadata and a pre-signed S3 URL (if ready) | `artifact_id` | `artifact_id`, `status`, `signed_url`, `type`, `metadata` |
| `poll_artifact` | Block until artifact is ready or timeout reached (polls every 2 s) | `artifact_id`, `timeout_s` (default 60) | `artifact_id`, `status`, `signed_url`, `type`, `metadata` |
| `list_artifacts` | List artifacts with optional filters — metadata only, no URLs | `type`, `agent_id`, `date` (YYYY-MM-DD), `limit` (default 50) | list of artifact metadata |

## Artifact Types

| Type | Extension | Content-Type | Content Format |
|---|---|---|---|
| `chart` | `.jsx` | `text/jsx` | React/Recharts JSX component |
| `report` | `.md` | `text/markdown` | Markdown analysis report |
| `simulation_result` | `.json` | `application/json` | Simulation results with performance curve, Sharpe ratio, drawdown |
| `recommendation` | `.json` | `application/json` | Recommender output (action, target, confidence, rationale) |
| `image` | `.png` | `image/png` | Base64-encoded PNG (decoded to raw bytes before S3 upload) |
| `data_export` | `.csv` | `text/csv` | Time-series, allocation, or summary data |

## S3 Key Convention

Each artifact is stored at:

```
{artifact_id}/artifact{extension}
```

For example: `3f2a1b4c-8d9e-4f0a-b1c2-d3e4f5a6b7c8/artifact.json`

## DynamoDB Schema

Table: `mcp_artifacts`

| Attribute | Type | Notes |
|---|---|---|
| `artifact_id` | String (PK) | UUID v4 |
| `type` | String | One of the 6 artifact types |
| `status` | String | `processing` → `ready` or `error` |
| `s3_key` | String | `{artifact_id}/artifact{ext}` |
| `agent_id` | String | Optional, used by GSI2 |
| `execution_id` | String | Maps to Step Functions execution ID |
| `created_at` | String | ISO 8601 UTC |
| `metadata` | String | JSON-serialised dict |
| `idempotency_key` | String | Optional, scanned on write |

Global Secondary Indexes:
- **GSI1** `type-created_at-index` — query by type, sorted by time descending
- **GSI2** `agent_id-created_at-index` — query by agent, sorted by time descending

## Artifact Lifecycle

```
create_artifact(type, content)
    ├─ catalog.create_entry(status=processing)
    ├─ storage.put_object(s3_key, body, content_type)
    └─ catalog.update_status(status=ready)  # or error on failure

get_artifact(artifact_id)
    ├─ catalog.get_entry(artifact_id)
    └─ storage.generate_signed_url(s3_key)  # only if status=ready

poll_artifact(artifact_id, timeout_s=60)
    └─ loops get_entry every 2 s until ready/error/not_found or timeout
```

## Claim-Check Pattern

This MCP implements the claim-check pattern required by AWS Step Functions (256 KB payload limit):

```
Agent produces output
    → create_artifact(content) → S3 storage
    → Returns artifact_id (small UUID key)
    → artifact_id passes through Step Functions state machine
    → Downstream agent calls get_artifact(artifact_id)
    → Full content retrieved from S3
```

## Idempotency

All write operations support an idempotency key to prevent duplicate artifact creation on agent retries:

```python
idempotency_key = f"{agent_id}:{execution_id}:create_artifact:{param_hash}"
result = create_artifact(type="report", content=..., idempotency_key=idempotency_key)
```

If an artifact with the same key already exists, the existing artifact is returned without creating a new one.

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `AWS_DEFAULT_REGION` | Yes | — | AWS region (e.g. `eu-west-1`) |
| `AWS_ACCESS_KEY_ID` | Yes* | — | AWS credential (IAM role preferred) |
| `AWS_SECRET_ACCESS_KEY` | Yes* | — | AWS credential (IAM role preferred) |
| `S3_BUCKET` | No | `mcp-artifacts` | Override S3 bucket name |
| `DYNAMODB_TABLE` | No | `mcp_artifacts` | Override DynamoDB table name |

*In ECS Fargate, credentials are injected via IAM task role — no explicit key/secret needed.

Signed URL expiry is 3600 seconds (1 hour), defined in `storage.py`.

## Running Locally

**Docker Compose (recommended — includes LocalStack)**

```bash
docker compose up
```

This starts:
- `mcp-artifacts` on port 8080 (MCP server)
- `localstack` on port 4566 (local S3 + DynamoDB)

**Docker standalone**

```bash
docker build -t mcp-artifacts .
docker run -p 8004:8080 \
  -e AWS_DEFAULT_REGION=eu-west-1 \
  -e S3_BUCKET=platform-artifacts \
  mcp-artifacts
```

**Development (stdio transport)**

```bash
pip install -e ".[dev]"
mcp-artifacts
# or
python -m mcp_artifacts.server
```

## Development

```bash
pip install -e ".[dev]"       # Install with dev dependencies

ruff check . && ruff format . # Lint and format
mypy src/                     # Type check
pytest -v                     # Run tests (uses moto — no real AWS calls)
pytest --cov=mcp_artifacts    # Run tests with coverage
```

Tests use `moto` to mock S3 and DynamoDB — no AWS account required. All tools accept injected `storage` and `catalog` instances for isolation.

## Integration

This server is the output bus for every agent:

| Consumer | How it uses artifacts-mcp |
|---|---|
| Gap Detection Agent | Stores `ranked_gaps` JSON as `simulation_result` |
| Analytics Agent | Stores `analytics_report` as `report` |
| Recommender Agent | Stores `recommendation` JSON |
| Strategy Evaluation Agent | Stores simulation results as `simulation_result` |
| charting-mcp | Stores generated React/Recharts components as `chart` |
| Step Functions | Passes `artifact_id` strings between states |
| Claude.ai UI | Retrieves `chart` artifacts via signed URL for rendering |

## Deployment

**Production**: ECS Fargate, deployed by `agent-infra` McpStack CDK stack.
**Transport**: Streamable HTTP (production), stdio (development).
**Port: 8004. Container listens on 8080.

The Dockerfile uses `python:3.11-slim`, installs the package, and runs `mcp-artifacts` (the console script entry point defined in `pyproject.toml`).

## Project Structure

```
src/mcp_artifacts/
    __init__.py          # Version: 0.1.0
    server.py            # MCP server entrypoint, tool definitions, dispatcher
    schemas.py           # Pydantic models: ArtifactType, ArtifactMeta, CreateResult, ArtifactResult
    storage.py           # ArtifactStorage: S3 put_object, generate_signed_url, head_object
    catalog.py           # ArtifactCatalog: DynamoDB CRUD, GSI queries, table bootstrap
    tools/
        create.py        # create_artifact — idempotency check, S3 upload, status lifecycle
        get.py           # get_artifact — catalog lookup, signed URL generation
        poll.py          # poll_artifact — async polling loop (2 s interval)
        list_artifacts.py # list_artifacts — GSI queries with type/agent/date filters
tests/
    conftest.py          # Fixtures: mock_s3, mock_dynamodb, mock_aws_all (moto)
    test_create.py       # All 6 artifact types + idempotency + invalid type
    test_get.py          # get_artifact + poll_artifact: ready, not_found, processing, error
    test_catalog.py      # list_artifacts filters + direct catalog CRUD
```

## Phase

Phase 1, Plan P06 — Universal output pipeline, required by all Phase 1+ agents.
