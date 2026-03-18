# prompt-registry

> Prompt Registry — versioned prompt management service

Versioned prompt management service for agent platforms. Stores all agent and MCP prompt text in S3 and exposes a Lambda + API Gateway HTTP API for creation, resolution, promotion, rollback, and diffing. Every prompt is versioned in DynamoDB with a lifecycle (`draft` → `stable` → `deprecated`) and mode-gated access so draft prompts never reach production agents.

## Architecture Role

Prompt Registry enforces **Non-Negotiable Rule #1** — zero hardcoded prompts across the entire platform:

```
INTERACTION    →  Claude.ai / Custom UI
     ↕
MCP SKILLS     →  All MCPs load prompts from here at runtime
     ↕
AGENTS         →  All Strands agents load system prompts from here at startup
     ↕
ORCHESTRATION  →  Step Functions invokes prompt-resolve Lambda before agent calls
     ↕
EXECUTION CONTROL →  N/A
```

Every agent in the platform calls this service to obtain its `system_prompt`. No prompt text is ever hardcoded in application code or blueprints.

## Features

- **Semver versioning** — every prompt change creates a new immutable version
- **Promotion workflow** — `draft` → `stable` with automatic deprecation of the previous stable
- **Instant rollback** — restore any prior version to stable without a deployment
- **Mode-gated resolution** — draft prompts are blocked in `staging`/`production` mode; accessible in `simulation`/`dev`
- **Unified diff** — compare any two versions via unified diff output
- **Flexible ref syntax** — resolve by plain name, `name_vX.Y.Z`, or `name@X.Y.Z`
- **Dual storage** — text content in S3 (`{prompt_id}/{version}.txt`), metadata in DynamoDB
- **API Gateway proxy integration** — Lambda handler routes all HTTP methods
- **Moto-powered tests** — full test coverage with mocked AWS (no real AWS required)

## API Reference

| Method | Route | Description |
|---|---|---|
| `POST` | `/prompts` | Create a new prompt version (starts as `draft`) |
| `GET` | `/prompts/{prompt_id}` | Resolve prompt by ID — returns latest stable, or pinned version via `?version=` |
| `GET` | `/prompts/{prompt_id}/versions` | List all versions for a prompt with status and metadata |
| `POST` | `/prompts/{prompt_id}/promote` | Promote a version to `stable`; deprecates current stable |
| `POST` | `/prompts/{prompt_id}/rollback` | Rollback to a specific version; deprecates current stable |
| `GET` | `/prompts/{prompt_id}/diff` | Unified diff between two versions via `?v1=X&v2=Y` |

### Query Parameters for GET /prompts/{prompt_id}

| Parameter | Default | Description |
|---|---|---|
| `version` | — | Pin to a specific semver (e.g. `1.2.0`). Omit to get latest stable. |
| `mode` | `production` | Execution mode: `simulation`, `dev`, `staging`, `production`. Draft prompts only visible in `simulation` and `dev`. |

### Response Codes

| Code | Meaning |
|---|---|
| `200` | Success |
| `201` | Prompt version created |
| `400` | Invalid request body or missing parameters |
| `404` | Prompt or version not found |
| `409` | Version already exists for this prompt_id |
| `500` | Internal error |

## Data Models

```python
class PromptStatus(str, Enum):
    DRAFT = "draft"
    STABLE = "stable"
    DEPRECATED = "deprecated"

class PromptVersion(BaseModel):
    prompt_id: str
    version: str          # semver, e.g. "1.2.0"
    description: str
    status: PromptStatus
    s3_key: str           # e.g. "gap_detector/1.2.0.txt"
    created_at: str       # ISO 8601 UTC
    updated_at: str       # ISO 8601 UTC
    tags: list[str]

class PromptCreateRequest(BaseModel):
    prompt_id: str
    version: str
    text: str
    description: str = ""
    tags: list[str] = []

class PromptPromoteRequest(BaseModel):
    version: str

class PromptRollbackRequest(BaseModel):
    version: str

class PromptResolveResponse(BaseModel):
    prompt_id: str
    version: str
    text: str
    status: PromptStatus

class PromptVersionListItem(BaseModel):
    prompt_id: str
    version: str
    description: str
    status: PromptStatus
    created_at: str
    tags: list[str]
```

## Prompt Reference Syntax

The resolver supports three formats for pinning a prompt version:

| Format | Example | Resolves to |
|---|---|---|
| Plain name | `gap_detector` | Latest `stable` version |
| Underscore-v | `gap_detector_v1.2` | Version `1.2.0` (zero-padded automatically) |
| Underscore-v full semver | `gap_detector_v1.2.0` | Version `1.2.0` exact |
| At-sign | `gap_detector@2.0.0` | Version `2.0.0` exact |

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `DYNAMODB_TABLE` | Yes | `prompt_registry` | DynamoDB table name |
| `S3_BUCKET` | Yes | `prompt-registry` | S3 bucket name |
| `AWS_DEFAULT_REGION` | Yes | — | AWS region (use `eu-west-1` for production) |

## Usage

### Resolving a Prompt in an Agent

```python
import boto3
import json

# Call the Prompt Registry API directly
import urllib.request

API_BASE = "https://<api-id>.execute-api.eu-west-1.amazonaws.com/prod"

def resolve_prompt(prompt_id: str, mode: str = "production") -> str:
    url = f"{API_BASE}/prompts/{prompt_id}?mode={mode}"
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    return data["text"]

# In your Strands agent
system_prompt = resolve_prompt("gap_detector")
agent = Agent(system_prompt=system_prompt, tools=[...])
```

### Resolving a Pinned Version

```python
# Pin to a specific version (e.g. in a workflow that must be deterministic)
url = f"{API_BASE}/prompts/gap_detector?version=1.2.0&mode=production"
```

### Creating a New Prompt Version

```python
import json, urllib.request

payload = json.dumps({
    "prompt_id": "gap_detector",
    "version": "1.3.0",
    "text": "You are an expert gap detector...",
    "description": "Improved gap scoring logic",
    "tags": ["gap", "v1"],
}).encode()

req = urllib.request.Request(
    f"{API_BASE}/prompts",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    print(json.loads(resp.read()))
# {"message": "Prompt version created", "prompt_id": "gap_detector", "version": "1.3.0", "status": "draft"}
```

### Promoting to Stable

```python
payload = json.dumps({"version": "1.3.0"}).encode()
req = urllib.request.Request(
    f"{API_BASE}/prompts/gap_detector/promote",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
# Promotes 1.3.0 to stable; 1.2.0 is automatically deprecated
```

### Rolling Back

```python
payload = json.dumps({"version": "1.2.0"}).encode()
req = urllib.request.Request(
    f"{API_BASE}/prompts/gap_detector/rollback",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
# Restores 1.2.0 to stable instantly; 1.3.0 is deprecated
```

### Diffing Two Versions

```python
url = f"{API_BASE}/prompts/gap_detector/diff?v1=1.2.0&v2=1.3.0"
# Returns unified diff of the two prompt texts
```

## Versioning Lifecycle

```
POST /prompts         →  version created as "draft"
POST .../promote      →  version becomes "stable"; previous stable → "deprecated"
POST .../rollback     →  target version becomes "stable"; current stable → "deprecated"
```

- Only one version is `stable` at any time per `prompt_id`
- Deprecated versions remain accessible by pinned reference in `simulation`/`dev` mode
- Deprecated versions are blocked from resolution in `staging`/`production` mode

## Mode-Gated Access

| Mode | Stable | Draft | Deprecated |
|---|---|---|---|
| `production` | Accessible | Blocked | Blocked |
| `staging` | Accessible | Blocked | Blocked |
| `simulation` | Accessible | Accessible | Blocked |
| `dev` | Accessible | Accessible | Blocked |

This ensures agents running in production never accidentally consume untested prompt versions.

## Storage Layout

- **S3 bucket** (`prompt-registry`): Prompt content stored as `{prompt_id}/{version}.txt`
- **DynamoDB table** (`prompt_registry`): Prompt metadata with composite key `prompt_id` (hash) + `version` (range)

## Package

Published as `prompt-registry` v0.1.0 to AWS CodeArtifact for use as a library by platform repos.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests (no real AWS required — moto mocks all AWS calls)
pytest tests/ -v

# Lint
ruff check src/
ruff format --check src/

# Type check
mypy src/
```

## Deployment

Deployed as a Lambda function + API Gateway (HTTP proxy integration) via the `agent-infra` CDK stack (`AgentStack`). The Lambda handler entry point is `prompt_registry.handler.handler`.

On every push to `main` that modifies `src/` or `pyproject.toml`, the `publish.yml` workflow builds and publishes the package to AWS CodeArtifact automatically.

## Module Structure

```
src/prompt_registry/
├── __init__.py       # package version
├── models.py         # Pydantic models: PromptVersion, requests, responses, Mode enum
├── registry.py       # DynamoDB CRUD: put, get, list, promote, rollback, update_status
├── storage.py        # S3 read/write: put (returns s3_key), get, delete
├── resolver.py       # Reference parsing and mode-gated resolution logic
└── handler.py        # Lambda entry point — routes API Gateway proxy events

tests/
├── conftest.py               # moto fixtures: DynamoDB table, S3 bucket, combined mock
├── test_registry.py          # Registry CRUD, promote, rollback, version sorting
├── test_resolver.py          # Reference parsing (all formats), mode gating, latest/pinned
├── test_handler.py           # Full API surface via Lambda handler (create, get, list, promote, rollback, diff)
└── fixtures/sample_prompts/  # Sample prompt text files for test seeding
```

## Compliance and Safety

- Satisfies **Non-Negotiable Rule #1**: zero hardcoded prompts across the entire platform
- Prompt versioning provides a complete audit trail of all agent instructions over time
- Version locking (`name@X.Y.Z`) prevents unintended prompt drift in production Step Functions workflows
- Mode enforcement (`staging`/`production` blocks drafts) prevents accidental use of untested prompts in production operations

## Phase

Phase 1 (P04 — Prompt Registry, P09 — Analytics Agent dependency). Required before any Strands agent can be deployed.
