---
title: Memory
nav_order: 4
parent: SDK Reference
---

# Memory

The Memory subsystem provides a two-tier storage model for agent conversations. Short-term memory holds raw events with a TTL. Long-term memory persists distilled knowledge in a pgvector index for semantic retrieval across sessions.

Memory integrates with the agent lifecycle through hook events, so it populates automatically as the agent runs — no explicit `save` calls required.

## Key Classes

| Class | Purpose |
|-------|---------|
| `MemoryManager` | Top-level interface — create events, retrieve turns, and semantic search |
| `MemoryHookProvider` | Strands hook that intercepts agent events and writes to memory |
| `MemoryBranchManager` | Fork conversations into named branches for multi-agent coordination (wraps `MemorySessionManager`) |
| `MemoryToolProvider` | Exposes `memory_recall` and `memory_record` as agent-callable tools |

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
| `EPISODIC` | Stores episodic memories of discrete events |

Blueprint configuration:

```yaml
memory:
  strategies:
    - type: SEMANTIC
      name: "semantic-extraction"
      namespace: "user/{actorId}"
  event_expiry_days: 30
  short_term_k: 5
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
  strategies:
    - type: SEMANTIC
      name: "user-memory"
      namespace: "user/{actorId}/agent/{agentName}"
```

At runtime, `{actorId}` is resolved from the verified identity claims and `{agentName}` from the blueprint. This ensures memory from one user never leaks to another.

## Branching for Multi-Agent

`MemoryBranchManager` wraps `bedrock_agentcore.memory.MemorySessionManager` to provide isolated memory contexts for sub-agents. Each specialist gets a forked conversation branch that can be read independently:

```python
from agent_core.memory.branching import MemoryBranchManager

branch_mgr = MemoryBranchManager(memory_id="mem-abc123")

# Create a session, then fork a branch for a specialist
session = branch_mgr.create_session(actor_id="coordinator", session_id="sess-1")
branch_mgr.fork_conversation(
    session=session,
    root_event_id="evt-000",
    branch_name="summarization-task",
    messages=[("Summarize the document", "user")],
)

# Read specialist branch turns
turns = branch_mgr.get_branch_turns(session, branch_name="summarization-task", k=10)

# List all branches
branches = branch_mgr.list_branches(session)
```

## Direct Read and Write

For cases where explicit control is needed:

```python
from agent_core.memory.manager import MemoryManager

memory = MemoryManager(memory_id="mem-abc123")

# Store conversation turns as events
memory.create_event(
    memory_id="mem-abc123",
    actor_id="user-u-123",
    session_id="sess-001",
    messages=[("What is the weather?", "user"), ("It is sunny today.", "assistant")],
)

# Retrieve recent short-term turns
turns = memory.get_last_k_turns(
    memory_id="mem-abc123",
    actor_id="user-u-123",
    session_id="sess-001",
    k=5,
)

# Semantic search in extracted long-term memories
results = memory.retrieve_memories(
    memory_id="mem-abc123",
    namespace="user/u-123",
    query="user's preferred communication style",
    top_k=5,
)
for result in results:
    print(result)
```

## Agent-Callable Memory Tools

When `memory.enable_tool_provider: true` is set in the blueprint, `MemoryToolProvider` (wrapping `AgentCoreMemoryToolProvider` from `strands_tools`) exposes `memory_recall` and `memory_record` as tools the agent can call directly — in addition to the automatic hook-based persistence:

```python
from agent_core.memory.tool_provider import MemoryToolProvider

tool_provider = MemoryToolProvider(
    memory_id="mem-abc123",
    actor_id="agent-1",
    session_id="sess-001",
)

agent = Agent(model=model, tools=[*other_tools, *tool_provider.tools])
```

## Multi-Namespace Retrieval

The `RetrievalConfig` schema supports per-namespace `top_k` and `relevance_score` thresholds. Configure multiple namespaces in the blueprint to search different memory scopes during agent initialization:

```yaml
memory:
  retrieval:
    - namespace: "user/{actorId}/preferences"
      top_k: 3
      relevance_score: 0.5
    - namespace: "user/{actorId}/history"
      top_k: 10
      relevance_score: 0.3
```

Each namespace is searched independently and results are merged before injection into the agent context.

## Blueprint Configuration

```yaml
memory:
  strategies:
    - type: SEMANTIC
      name: "semantic-extraction"
      namespace: "user/{actorId}"
    - type: USER_PREFERENCE
      name: "pref-extraction"
      namespace: "user/{actorId}/prefs"
  event_expiry_days: 30
  short_term_k: 5
  enable_tool_provider: false
  retrieval:
    - namespace: "user/{actorId}"
      top_k: 10
      relevance_score: 0.3
```

All model IDs come from the blueprint — the SDK never supplies a default model.
