---
title: Prompt Registry
nav_order: 11
parent: SDK Reference
---

# Prompt Registry

The Prompt Registry provides versioned, environment-aware management of agent prompts. Prompts move through a lifecycle (draft → active → archived) and are resolved at runtime based on the deployment mode — so a staging environment can use different prompt versions than production without code changes.

## Concepts

### Versioning Lifecycle

Every prompt version follows a three-state lifecycle:

```
draft → active → archived
```

- **draft**: Work in progress. Never served to production traffic. Safe for iteration and review.
- **active**: The version currently served. Only one version per prompt can be active at a time in each mode. Promoting a new version atomically deactivates the previous one.
- **archived**: Historical versions. Readable for audit and rollback, not served.

### Mode-Gated Resolution

The registry distinguishes three deployment modes:

| Mode | Typical Environment | Behavior |
|------|--------------------|---------:|
| `simulation` | Local / CI | Resolves the latest draft or active version |
| `staging` | Pre-production | Resolves the active version for staging |
| `production` | Production | Resolves the active version for production |

Modes ensure a prompt can be validated in staging before going live, and that simulation environments pick up draft changes immediately.

## PromptRegistryClient

```python
from prompt_registry import PromptRegistryClient

client = PromptRegistryClient.from_env()
```

The client reads its configuration from environment variables set by the platform's Terraform deployment.

## API Reference

### push

Upload a new draft version of a prompt:

```python
version_id = await client.push(
    name="customer-greeting",
    content="You are a helpful assistant. Greet the user warmly and ask how you can help.",
    metadata={"author": "platform-team", "ticket": "PLAT-42"},
)
print(version_id)  # "customer-greeting:v5"
```

A pushed version always starts in `draft` state.

### get

Retrieve a prompt, resolved for the current mode:

```python
# Resolves active version for the current deployment mode
prompt = await client.get("customer-greeting")

# Resolve a specific version explicitly
prompt = await client.get("customer-greeting", version="v3")

# Resolve for a specific mode
prompt = await client.get("customer-greeting", mode="staging")

print(prompt.content)
print(prompt.version)   # "v5"
print(prompt.state)     # "active"
```

### list

List all versions of a prompt:

```python
versions = await client.list("customer-greeting")
for v in versions:
    print(v.version, v.state, v.created_at)
```

### diff

Show the text diff between two versions:

```python
diff = await client.diff("customer-greeting", from_version="v3", to_version="v5")
print(diff.unified_diff)
```

### promote

Move a draft version to active for a specific mode:

```python
await client.promote(
    name="customer-greeting",
    version="v5",
    mode="staging",
)
```

Promotion is atomic: the previous active version for that mode moves to `archived` in the same operation. To promote to production, call promote again with `mode="production"` after validating in staging.

### rollback

Reactivate a previously archived version:

```python
await client.rollback(
    name="customer-greeting",
    to_version="v3",
    mode="production",
)
```

Rollback follows the same atomic swap — the current active version archives, and `v3` becomes active.

## Data Models

### PromptVersion

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Prompt name (immutable identifier) |
| `version` | `str` | Version string (e.g., `"v5"`) |
| `content` | `str` | Prompt text |
| `state` | `str` | `draft`, `active`, or `archived` |
| `mode` | `str` | Mode this version is active in, or `None` if draft/archived |
| `metadata` | `dict` | Arbitrary key-value metadata |
| `created_at` | `datetime` | Creation timestamp |
| `promoted_at` | `datetime \| None` | Timestamp of last promotion |

## Blueprint Integration

Agents reference prompts by name in their blueprint. The runtime resolves the correct version at startup:

```yaml
# agent.yaml
prompts:
  system: "customer-greeting"
  tool_use_instructions: "tool-calling-guide"
  error_recovery: "error-recovery-v2"
```

At runtime, `AgentCoreApp.from_blueprint` calls `client.get(name)` for each declared prompt and injects the resolved content into the agent's system prompt.

## Promotion Workflow

The recommended workflow for updating a production prompt:

```bash
# 1. Push a new draft
agent-cli prompts push customer-greeting --file new-greeting.txt

# 2. Review the diff
agent-cli prompts diff customer-greeting --from active --to latest-draft

# 3. Promote to staging and validate
agent-cli prompts promote customer-greeting --mode staging

# 4. After validation, promote to production
agent-cli prompts promote customer-greeting --mode production
```

See the [CLI reference](../cli/) for the full `agent-cli prompts` command set.

## Infrastructure

The Prompt Registry Lambda and Function URL are deployed by the platform's `prompt_registry` Terraform submodule. The `PROMPT_REGISTRY_URL` environment variable is auto-injected into all agent and MCP runtimes when `prompt_registry_url` is passed to the agents module.

See [Prompt Registry Module]({{ '/docs/infrastructure/prompt-registry-module' | relative_url }}) for deployment details, input variables, and domain seeding patterns.
