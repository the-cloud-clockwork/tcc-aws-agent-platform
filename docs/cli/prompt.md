---
title: prompt
nav_order: 2
parent: CLI Reference
---

# agentcli prompt

Manage versioned prompt templates in the Prompt Registry. Supports the full lifecycle: push a new version, inspect and diff versions, promote to `stable`, and rollback if a bad version ships.

Prompt versions move through three statuses: `draft` (newly pushed, only accessible in `simulation` and `dev` execution modes), `stable` (the active production version resolved when no explicit version is specified), and `deprecated` (a previous stable version demoted by a promote or rollback).

The CLI communicates with the Prompt Registry API over HTTP. Set `AGENT_REGISTRY_URL` to point at your registry instance (e.g., the API Gateway URL for the deployed Prompt Registry Lambda).

## Synopsis

```
agentcli prompt <subcommand> [OPTIONS] [ARGS]
```

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `push` | Upload a prompt template file as a new version |
| `get` | Fetch and display a prompt version |
| `list` | List all versions of a prompt with their status |
| `diff` | Show a unified diff between two versions |
| `promote` | Promote a version to stable status |
| `rollback` | Rollback to a previous version (marks it stable, demotes current) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_REGISTRY_URL` | `http://localhost:8000` | Prompt Registry API base URL |

## agentcli prompt push

Upload a prompt template to the registry as a new version.

```
agentcli prompt push FILE --id PROMPT_ID --version VERSION
```

### Options

| Option | Required | Description |
|--------|----------|-------------|
| `--id` | Yes | Prompt identifier (e.g., `my-agent-system`) |
| `--version` | Yes | Semantic version string (e.g., `1.2.0`) |

### Example

```bash
agentcli prompt push prompts/system.jinja2 \
  --id my-agent-system \
  --version 1.2.0
# Pushed prompt my-agent-system v1.2.0
```

## agentcli prompt get

Fetch and display a prompt template. Renders the content in a syntax-highlighted panel.

```
agentcli prompt get PROMPT_ID [--version VERSION]
```

### Options

| Option | Description |
|--------|-------------|
| `--version` | Specific version to fetch (default: latest stable) |

### Example

```bash
# Get latest stable version
agentcli prompt get my-agent-system

# Get a specific version
agentcli prompt get my-agent-system --version 1.1.0
```

## agentcli prompt list

List all versions of a prompt, showing status and creation timestamp.

```
agentcli prompt list PROMPT_ID
```

### Example

```bash
agentcli prompt list my-agent-system
```

Output:

```
         Versions of prompt: my-agent-system
+---------+--------+----------------------+--------------+
| Version | Status | Created              | Hash         |
+---------+--------+----------------------+--------------+
| 1.2.0   | draft  | 2025-11-01T09:14:22Z | a3f8c1d2e9b4 |
| 1.1.0   | stable | 2025-10-15T14:30:00Z | 7b2e4a9c1f83 |
| 1.0.0   | stable | 2025-09-20T10:00:00Z | 4d1c9e7a2f56 |
+---------+--------+----------------------+--------------+
```

## agentcli prompt diff

Show a unified diff between two versions of the same prompt.

```
agentcli prompt diff PROMPT_ID VERSION_A VERSION_B
```

### Example

```bash
agentcli prompt diff my-agent-system 1.1.0 1.2.0
```

Output shows a syntax-highlighted unified diff of the prompt content.

## agentcli prompt promote

Promote a version to `stable` status. The `stable` version is what agents resolve when no explicit version is specified.

```
agentcli prompt promote PROMPT_ID VERSION
```

### Example

```bash
agentcli prompt promote my-agent-system 1.2.0
# Promoted prompt my-agent-system v1.2.0 to stable
```

## agentcli prompt rollback

Rollback a prompt to a previous version. This marks the target version as `stable` and demotes the current stable version.

```
agentcli prompt rollback PROMPT_ID VERSION
```

### Example

```bash
agentcli prompt rollback my-agent-system 1.1.0
# Rolled back prompt my-agent-system to v1.1.0
```

## Complete Workflow Example

This example shows a typical prompt development cycle:

```bash
# 1. Push a new version (status: draft)
agentcli prompt push prompts/system.jinja2 \
  --id my-agent-system \
  --version 1.2.0

# 2. Review what changed from the previous stable version
agentcli prompt diff my-agent-system 1.1.0 1.2.0

# 3. Check the new version renders correctly
agentcli prompt get my-agent-system --version 1.2.0

# 4. List all versions to confirm state before promoting
agentcli prompt list my-agent-system

# 5. Promote to stable — agents will now resolve this version
agentcli prompt promote my-agent-system 1.2.0

# 6. Something went wrong in production — rollback immediately
agentcli prompt rollback my-agent-system 1.1.0
```

## See Also

- [Prompts](../runtime/prompts) — lifecycle (draft → stable → deprecated), version pinning, mode-gating, and resolution order
- [Prompts SDK Reference](../sdk/prompts) — programmatic access to the Prompt Registry via `PromptRegistryClient`
- [Agent Blueprint](../blueprints/agent-blueprint) — how blueprints reference prompt versions with `prompt_ref`
