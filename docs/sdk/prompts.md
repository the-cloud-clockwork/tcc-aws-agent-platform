---
title: Prompt Registry
nav_order: 11
parent: SDK Reference
---

# Prompt Registry

The Prompt Registry provides versioned, environment-aware management of agent system prompts. Prompts move through a three-state lifecycle and are resolved at runtime based on the deployment mode — staging environments pick up different versions than production without any code changes.

> **Architecture guide:** [Runtime & Memory](../runtime.md)

## Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `PromptRegistryClient` | `agent_core.prompt.client` | Runtime prompt resolution — three-tier resolution order |

## Versioning Lifecycle

```
draft → stable → deprecated
```

| Status | Description |
|--------|-------------|
| `draft` | Work in progress. Accessible in `simulation` and `dev` modes only. Never served to staging or production. |
| `stable` | The version currently served. Only one version per prompt can be stable at a time. Promotion atomically deprecates the previous stable version. |
| `deprecated` | Historical versions. Readable for audit and rollback, not served to live traffic. |

## Mode-Gated Resolution

| Mode | Draft Allowed | Resolves |
|------|--------------|---------|
| `simulation` | Yes | Latest draft or stable version |
| `dev` | Yes | Latest draft or stable version |
| `staging` | No | Latest stable version |
| `production` | No | Latest stable version |

## `PromptRegistryClient`

```python
class PromptRegistryClient:
    def __init__(
        self,
        registry_url: str | None = None,           # Fallback: PROMPT_REGISTRY_URL env var
        lambda_function_name: str | None = None,   # Fallback: PROMPT_REGISTRY_FUNCTION env var
        local_dir: str | Path | None = None,       # Local file fallback root
        timeout: float = 10.0,
    ) -> None: ...

    def get(self, prompt_ref: str) -> str:
        """Resolve a prompt to its text content.
        
        prompt_ref formats:
          "my-prompt"          — latest stable (or draft in simulation/dev)
          "my-prompt@v3"       — explicit version pin
          "my-prompt_v3"       — alternate pin syntax
        
        Returns the prompt text as a plain string.
        """
        ...
```

**There is no `from_env()` classmethod.** Environment variables are read in `__init__` via `os.environ.get`.

## Three-Tier Resolution Order

`PromptRegistryClient.get()` resolves prompts in this order (first success wins):

1. **Direct Lambda invoke** via `boto3` when `PROMPT_REGISTRY_FUNCTION` is set — the standard production path. Bypasses HTTP for lower latency and no Function URL exposure.
2. **HTTP GET** to `PROMPT_REGISTRY_URL` — used when the Lambda ARN is not available (external callers, cross-account).
3. **Local file fallback** from `local_dir/{prompt_ref}.txt` — for local development and CI without a deployed registry.

Set `PROMPT_REGISTRY_FUNCTION` to the Lambda function name in production environments.

## Version Pinning

```python
client = PromptRegistryClient()

# Latest stable version
text = client.get("customer-greeting")

# Pinned to a specific version
text = client.get("customer-greeting@v3")
text = client.get("customer-greeting_v3")   # Equivalent alternate syntax
```

## `PromptVersion` Data Model

| Field | Type | Description |
|-------|------|-------------|
| `prompt_id` | `str` | Prompt identifier (stored in DynamoDB as `prompt_key`) |
| `version` | `str` | Version string (e.g., `"v3"`) |
| `content` | `str` | Prompt text |
| `status` | `PromptStatus` | `draft`, `stable`, or `deprecated` |
| `description` | `str \| None` | Optional description |
| `tags` | `list[str]` | Optional tags |
| `created_at` | `datetime` | Creation timestamp |

## Prompt Registry Lambda API

The Lambda handler (in `modules/platform/modules/prompt_registry/`) is the authoritative server. The `PromptRegistryClient` accesses it via direct boto3 invoke or HTTP. The Lambda routes:

| HTTP Method | Path | Description |
|-------------|------|-------------|
| `POST` | `/prompts` | Create a new prompt version |
| `GET` | `/prompts/{id}` | Resolve a prompt (mode-gated) |
| `GET` | `/prompts/{id}/versions` | List all versions |
| `POST` | `/prompts/{id}/promote` | Atomically promote a draft to stable |
| `POST` | `/prompts/{id}/rollback` | Atomically roll back to a prior stable version |
| `GET` | `/prompts/{id}/diff` | Text diff between two versions |

Promote and rollback operations are DynamoDB conditional-expression gated — they are atomic swaps.

`PromptRegistryClient` only implements `get()`. The other operations are performed by the `agent-cli prompts` CLI commands or direct Lambda invocations.

## Blueprint Integration

Agents reference prompts by name in their blueprint. `BlueprintLoader` resolves the prompt text at agent load time:

```yaml
id: my-agent
prompt_ref: customer-greeting      # Resolves via PromptRegistryClient.get()
```

Env-template expansion is supported in `prompt_ref`:

```yaml
prompt_ref: "customer-greeting@${PROMPT_VERSION:-v1}"
```

## Promotion Workflow

```bash
# Push a new draft
agent-cli prompts push customer-greeting --file new-greeting.txt

# Review the diff against the current stable version
agent-cli prompts diff customer-greeting

# Promote to stable
agent-cli prompts promote customer-greeting

# Roll back to a previous version if needed
agent-cli prompts rollback customer-greeting --version v3
```

See the [CLI reference](../cli.md) for the full `agent-cli prompts` command set.

## Infrastructure

Prompt text is stored in S3 at `{prompt_id}/{version}.txt`. Metadata is stored in DynamoDB (`prompt_registry` table) with partition key `prompt_key`. The Lambda function ARN is available as Terraform output `prompt_registry_function_arn` from the platform module — pass it to `modules/agents` as `prompt_registry_function_arn` to grant agent roles `lambda:InvokeFunction` on the registry.

See [Infrastructure: Platform Module](../infrastructure/platform-module.md) for deployment details.
