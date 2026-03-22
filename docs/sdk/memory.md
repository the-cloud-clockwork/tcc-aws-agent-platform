---
title: Memory
nav_order: 4
---

# Memory

The Memory subsystem provides a two-tier storage model for agent conversations. Short-term memory holds raw events with a TTL. Long-term memory persists distilled knowledge in a pgvector index for semantic retrieval across sessions.

Memory integrates with the agent lifecycle through hook events, so it populates automatically as the agent runs — no explicit `save` calls required.

## Key Classes

| Class | Purpose |
|-------|---------|
| `MemoryManager` | Top-level interface — read, write, and search across both tiers |
| `MemoryHookProvider` | Strands hook that intercepts agent events and writes to memory |
| `MemoryBranchManager` | Fork and merge memory namespaces for multi-agent coordination |

## Two-Tier Architecture

### Short-Term Memory (Event Store)

Raw events — messages, tool calls, tool results, agent thoughts — stored with a configurable TTL. Events are written immediately after each agent step. They are queryable within the TTL window and available for context injection in subsequent turns of the same session.

### Long-Term Memory (Semantic Store)

Distilled knowledge extracted from short-term events by the memory strategy. Stored as embeddings in Amazon Bedrock AgentCore's managed pgvector store. Retrieved by semantic similarity at session start, so the agent enters each new conversation with relevant background.

## Strategy Types

The memory strategy controls what gets promoted from short-term to long-term storage:

| Strategy | Behavior |
|----------|---------|
| `USER_PREFERENCE` | Extracts stated preferences, recurring patterns, and explicit settings |
| `SEMANTIC` | Embeds and stores all significant turns for general-purpose retrieval |
| `SUMMARY` | Generates a rolling summary of each session; stores the summary |

Blueprint configuration:

```yaml
memory:
  enabled: true
  strategy: SEMANTIC
  short_term_ttl_hours: 24
  namespace: "user/{user_id}"
```

## Hook Pattern

`MemoryHookProvider` implements the Strands hook interface. Register it with the agent and it fires automatically on lifecycle events:

```python
from agent_core.memory import MemoryHookProvider

memory_hook = MemoryHookProvider.from_blueprint("agent.yaml")

agent = Agent(
    model=model,
    tools=tools,
    hooks=[memory_hook],
)
```

The hook responds to two key events:

**`AgentInitializedEvent`** — Fires when the agent starts. The hook retrieves the top-K semantically similar memories for the current user and namespace, and injects them as context.

**`MessageAddedEvent`** — Fires after each message turn. The hook writes the event to short-term storage and schedules distillation to long-term storage according to the configured strategy.

## Namespaces

Namespaces isolate memory between users, sessions, or agent roles. Namespaces support template variables resolved at runtime:

```yaml
memory:
  namespace: "user/{user_id}/agent/{agent_name}"
```

At runtime, `{user_id}` is resolved from the verified identity claims and `{agent_name}` from the blueprint. This ensures memory from one user never leaks to another.

## Branching for Multi-Agent

`MemoryBranchManager` supports coordinator/specialist patterns where a coordinator spawns specialist sub-agents. Each specialist gets a forked namespace that can read from the parent but writes to its own branch:

```python
from agent_core.memory import MemoryBranchManager

branch_manager = MemoryBranchManager(memory_manager)

# Fork a branch for a specialist agent
branch = await branch_manager.fork(
    parent_namespace="user/{user_id}",
    branch_name="summarization-task-{task_id}",
)

# After the specialist completes, merge selected facts back
await branch_manager.merge(branch, strategy="selective", tags=["key-finding"])
```

Branches are cheap — they share the parent's read index until a write occurs (copy-on-write semantics).

## Direct Read and Write

For cases where explicit control is needed:

```python
from agent_core.memory import MemoryManager

memory = MemoryManager.from_blueprint("agent.yaml")

# Write an event directly
await memory.write_event(
    namespace="user/u-123",
    event_type="preference",
    content={"theme": "dark", "language": "en"},
)

# Semantic search in long-term memory
results = await memory.search(
    namespace="user/u-123",
    query="user's preferred communication style",
    top_k=5,
)
for result in results:
    print(result.content, result.score)
```

## Blueprint Configuration

```yaml
memory:
  enabled: true
  strategy: SEMANTIC           # USER_PREFERENCE | SEMANTIC | SUMMARY
  short_term_ttl_hours: 24
  long_term_top_k: 10
  namespace: "user/{user_id}"
  distillation_model: anthropic.claude-3-haiku-20240307-v1:0
```

All model IDs come from the blueprint — the SDK never supplies a default model.
