---
title: Prompts
nav_order: 4
parent: "Runtime & Memory"
---

# Prompt Registry

The Prompt Registry is a versioned prompt management service. Prompt text is stored in **S3**; metadata (version, status, timestamps, tags) is stored in **DynamoDB**. The registry provides a lifecycle for prompts and mode-gated resolution so agents in different execution environments use different prompt versions without code changes.

## Why a Registry

Hardcoding prompts in blueprint YAML or application code creates several problems:

- No versioning — rolling back a prompt change requires a code deployment
- No environment separation — the same prompt runs in simulation and production
- No audit trail — prompt changes are buried in git history alongside code
- No A/B testing — comparing variants requires code branches

The Prompt Registry treats prompts as first-class versioned artifacts with their own lifecycle.

## Storage Model

- **S3** stores the prompt text at key `{prompt_id}/{version}.txt`. Prompt text can be large (multi-page system prompts) — S3 handles this without DynamoDB item size limits.
- **DynamoDB** stores metadata with partition key `prompt_key` (the prompt ID) and sort key `version`. Fields: `prompt_id`, `version`, `description`, `status`, `s3_key`, `created_at`, `updated_at`, `tags`.

## Lifecycle

Prompts follow a three-state lifecycle:

```
draft ──promote──> stable ──promote──> deprecated
  ^                                         |
  └──────────────rollback──────────────────┘
```

| Status | Meaning |
|--------|---------|
| `draft` | Work in progress. Only visible in `simulation` and `dev` execution modes. Never served in staging or production. |
| `stable` | The active version. Only one version per prompt can be `stable` at a time. |
| `deprecated` | Superseded by a newer stable version. Readable for audit; not served in normal resolution. |

**Note:** The status values are `draft`, `stable`, and `deprecated`. The terms "active" and "archived" are not used in the codebase.

### Promotion and Rollback

Promotion is **atomic**: `promote(prompt_id, version)` first deprecates the current stable version, then marks the target version as stable — in the same DynamoDB conditional-expression operation. Rollback follows the same atomic swap.

## Mode-Gated Resolution

The resolver enforces mode-based access rules:

| Execution mode | Behavior |
|---------------|---------|
| `simulation`, `dev` | Resolves latest `stable` version; falls back to latest `draft` if no stable exists |
| `staging`, `production` | Resolves latest `stable` version only; `draft` prompts are blocked |

This allows safe prompt iteration: test a new draft in simulation, promote to stable, validate in staging, then serve in production — all without code changes.

## Resolution Client

`PromptRegistryClient` is the SDK client for fetching prompt text. Its constructor reads configuration from environment variables; there is no `from_env()` classmethod.

```python
from agent_core.prompt.client import PromptRegistryClient

client = PromptRegistryClient()  # reads env vars in __init__
```

Constructor parameters and their environment variable sources:

| Parameter | Env var | Default |
|-----------|---------|---------|
| `registry_url` | `PROMPT_REGISTRY_URL` | `http://localhost:8080` |
| `lambda_function_name` | `PROMPT_REGISTRY_FUNCTION` | `""` (use HTTP) |
| `local_dir` | — | `None` |
| `timeout` | — | `10.0` seconds |

### Three-Tier Resolution Order

`client.get(prompt_ref)` resolves in this order:

1. **Direct Lambda invoke** (preferred in production): if `PROMPT_REGISTRY_FUNCTION` is set, calls the Lambda directly via `boto3.client('lambda').invoke()`. The native AWS credential chain handles SigV4 signing — the same chain that calls Bedrock and Gateway. This avoids the network hop through a Function URL.
2. **HTTP GET** to `{PROMPT_REGISTRY_URL}/prompts/{prompt_ref}` — for local development or non-Lambda registries.
3. **Local file fallback**: reads `{local_dir}/{prompt_ref}.txt` — for offline development without registry infrastructure.

If all three fail, `PromptResolutionError` is raised.

### Version Pinning

Two pinning formats are supported:

```python
# Latest stable
text = client.get("my-agent-prompt")

# Pinned: name@version format
text = client.get("my-agent-prompt@1.2.0")

# Pinned: name_vX.Y format
text = client.get("my-agent-prompt_v1.2")
```

An undecorated name resolves to the latest stable (or latest draft in simulation/dev mode). Pinned references target a specific version regardless of mode — though draft versions are still blocked in staging/production.

## CLI Operations

The `agentcli` tool provides prompt management commands:

```bash
# Push a new version (starts as draft)
agentcli prompt push my-agent-prompt --file prompt.txt --version 1.3.0

# Inspect the current stable version
agentcli prompt get my-agent-prompt

# View diff between versions
agentcli prompt diff my-agent-prompt --from 1.2.0 --to 1.3.0

# Promote draft to stable
agentcli prompt promote my-agent-prompt --version 1.3.0

# Rollback to a previous stable version
agentcli prompt rollback my-agent-prompt --version 1.1.0

# List all versions with status
agentcli prompt list my-agent-prompt
```

## Typical Promotion Workflow

```bash
# 1. Push a new draft
agentcli prompt push my-agent-prompt --file new-prompt.txt --version 1.3.0

# 2. Review the diff
agentcli prompt diff my-agent-prompt --from 1.2.0 --to 1.3.0

# 3. Test in simulation (draft is visible here automatically)

# 4. Promote to stable once validated
agentcli prompt promote my-agent-prompt --version 1.3.0
#    ^ atomically deprecates 1.2.0 and marks 1.3.0 as stable

# 5. Rollback if needed
agentcli prompt rollback my-agent-prompt --version 1.2.0
```

## Blueprint Integration

Agents reference prompts by ID in their blueprint via `prompt_ref`. The loader resolves the prompt text at startup using `PromptRegistryClient.get()`:

```yaml
# agent.yaml
id: my-agent
prompt_ref: my-agent-prompt   # resolves to latest stable
```

The `prompt_ref` value is passed directly to `PromptRegistryClient.get()`. Use the `name@version` or `name_vX.Y` format to pin to a specific version.

## Registry Lambda API

The Lambda handler is the authoritative runtime API. It exposes the following routes:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/prompts` | Create a new draft version (`PromptCreateRequest`: `prompt_id`, `version`, `content`, `description`, `tags`) |
| `GET` | `/prompts/{id}` | Resolve a prompt ref to text (mode-gated) |
| `GET` | `/prompts/{id}/versions` | List all versions with status |
| `POST` | `/prompts/{id}/promote` | Promote a version to stable |
| `POST` | `/prompts/{id}/rollback` | Rollback to a previous version |
| `GET` | `/prompts/{id}/diff` | Text diff between two versions |

`PromptRegistryClient` calls only `GET /prompts/{id}`. Mutations (push, promote, rollback) are CLI-only operations or direct Lambda invocations.

## Infrastructure

The Prompt Registry Lambda is deployed by the `prompt_registry` Terraform sub-module within `modules/platform`. The platform outputs `prompt_registry_function_arn` and `prompt_registry_function_name` — these must be passed to `modules/agents` to grant `lambda:InvokeFunction` to agent IAM roles.

See [Infrastructure — Platform Module](../infrastructure/platform-module) for deployment details.

## See Also

- [Prompt Registry SDK Reference](../sdk/prompts) — `PromptRegistryClient`, `PromptVersion` data model
- [CLI Reference](../cli/) — `agentcli prompt` commands
- [Infrastructure — Platform Module](../infrastructure/platform-module) — `prompt_registry` sub-module outputs
