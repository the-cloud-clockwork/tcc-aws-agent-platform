---
title: Prompts
parent: Concepts
nav_order: 11
---

# Prompt Registry

The Prompt Registry is a versioned prompt management service that stores prompt text in S3 with metadata in DynamoDB. It provides a lifecycle for prompts (draft, active, archived) and mode-gated resolution so that agents in different environments can use different prompt versions.

## Why a Registry

Hardcoded prompts create several problems:

- **No versioning** -- you cannot roll back a prompt change without a code deployment
- **No environment separation** -- the same prompt runs in simulation and production
- **No audit trail** -- changes to prompts are buried in git history alongside code changes
- **No A/B testing** -- comparing prompt variants requires code branches

The Prompt Registry solves these by treating prompts as first-class versioned artifacts.

## Storage Model

- **S3** stores the actual prompt text (potentially large, multi-page system prompts)
- **DynamoDB** stores metadata: prompt reference, version, status, mode bindings, timestamps

## Resolution

`PromptRegistryClient` resolves prompts with two strategies:

1. **Pinned version** -- `my_agent_v1.2` resolves to exactly that version
2. **Latest stable** -- `my_agent` resolves to the most recently promoted (active) version

The client calls `GET /prompts/{prompt_ref}` on the registry API (a Lambda-backed service). The registry URL is configured via `PROMPT_REGISTRY_URL` environment variable.

### Local Fallback

For local development, the client supports a `local_dir` parameter. If the registry API is unavailable, it falls back to reading `{local_dir}/{prompt_ref}.txt`. This keeps local development fast without requiring the full registry infrastructure.

## Lifecycle

Prompts follow a three-stage lifecycle:

1. **Draft** -- a new prompt version is pushed but not yet active
2. **Active** -- the prompt is promoted and becomes the default for its reference
3. **Archived** -- the prompt is superseded by a newer active version

### CLI Operations

The `agentcli` tool provides commands for managing prompts:

```bash
# Push a new prompt version (creates as draft)
agentcli prompt push my_agent --file prompt.txt

# Get the current active prompt
agentcli prompt get my_agent

# Promote a draft to active
agentcli prompt promote my_agent --version 1.2
```

## Mode-Gated Resolution

The registry supports mode-gated bindings so that a prompt reference resolves to different versions depending on the execution mode (simulation, staging, production). This enables safe prompt iteration: test a new prompt in simulation before promoting it to production.

## SDK Usage

```python
from agent_core.prompt.client import PromptRegistryClient

client = PromptRegistryClient()

# Resolve latest active version
prompt_text = client.get("my_agent")

# Resolve pinned version
prompt_text = client.get("my_agent_v1.2")
```
