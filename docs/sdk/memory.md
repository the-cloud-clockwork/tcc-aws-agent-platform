---
title: Memory
nav_order: 4
parent: SDK Reference
---

# Memory

The Memory subsystem provides a two-tier storage model for agent conversations. Short-term memory holds raw events with a TTL. Long-term memory persists strategy-extracted knowledge as pgvector embeddings for semantic retrieval across sessions.

Memory integrates with the agent lifecycle via Strands hook events — the hook fires automatically as the agent runs, with no explicit `save` calls required in agent code.

> **Architecture guide:** [Runtime & Memory](../runtime.md)

## Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `MemoryManager` | `agent_core.memory.manager` | Direct read/write interface — events, semantic search, session memory |
| `MemoryHookProvider` | `agent_core.memory.hook_provider` | Strands hook — auto-loads context on init, auto-persists turns |
| `MemoryBranchManager` | `agent_core.memory.branching` | Forks conversations into named branches for multi-agent coordination |
| `MemoryToolProvider` | `agent_core.memory.tool_provider` | Exposes `memory_recall` and `memory_record` as agent-callable tools |

## Two-Tier Architecture

### Short-Term Memory (Event Store)

Raw events (messages, tool calls, results, agent thoughts) stored with a configurable TTL via `MemoryClient.create_event()`. Events are retrieved at session start for context injection and kept for `event_expiry_days` (default: 30).

### Long-Term Memory (Semantic Store)

Distilled knowledge extracted from short-term events by the configured memory strategy. Stored as embeddings in AgentCore's managed pgvector store. Retrieved by semantic similarity at session start and injected as a `<memory_context>` block in the agent's system prompt.

Long-term extraction is **asynchronous** — `create_memory_and_wait()` triggers extraction and waits up to ~30 seconds for completion.

## Memory Wiring

`MemoryHookProvider` is a dataclass — **it has no `from_blueprint()` classmethod**. It is constructed automatically by `MemoryWiring` when `BlueprintLoader._wire_memory()` runs. Domain developers declare strategies in the blueprint; the hook is injected by the loader:

```yaml
memory:
  strategies:
    - type: SEMANTIC
      name: "semantic-extraction"
      namespace: "user/{actorId}"
  event_expiry_days: 30
  short_term_k: 5
```

`BlueprintLoader` constructs and registers `MemoryHookProvider` automatically. No manual instantiation is needed.

### For Direct Use (Advanced)

```python
from agent_core.memory.wiring import MemoryWiring
from agent_core.schemas.memory_config import MemoryConfig

wiring = MemoryWiring(
    config=MemoryConfig(strategies=[...]),
    memory_id=os.environ["AGENTCORE_MEMORY_ID"],
)

# Access the hook provider
hook = wiring.hook_provider

agent = Agent(model=model, tools=tools, hooks=[hook])
```

`AGENTCORE_MEMORY_ID` env var is required when strategies are declared. `BlueprintLoader._wire_memory()` raises `BlueprintLoadError` if it is missing.

## Strategy Types

| `type` | Behavior |
|--------|---------|
| `USER_PREFERENCE` | Extracts stated preferences, recurring patterns, and explicit settings |
| `SEMANTIC` | Embeds and stores all significant turns for general-purpose retrieval |
| `SUMMARY` | Generates a rolling summary per session; stores the summary |
| `EPISODIC` | Stores episodic memories of discrete events |

`SUMMARIZATION` is accepted as an alias for `SUMMARY` via a field validator.

## `MemoryManager`

Direct read/write interface for cases that need explicit control:

```python
from agent_core.memory.manager import MemoryManager

memory = MemoryManager(memory_id=os.environ["AGENTCORE_MEMORY_ID"])

# Write conversation turns
memory.create_event(
    memory_id="mem-abc123",
    actor_id="user-u-123",
    session_id="sess-001",
    messages=[
        ("What is the status of my order?", "user"),
        ("Your order is processing.", "assistant"),
    ],
)

# Retrieve recent short-term turns
turns = memory.get_last_k_turns(
    memory_id="mem-abc123",
    actor_id="user-u-123",
    session_id="sess-001",
    k=5,
)

# Semantic search over long-term extracted memories
results = memory.retrieve_memories(
    memory_id="mem-abc123",
    namespace="user/u-123",
    query="user's preferred communication style",
    top_k=5,
)

# Trigger async strategy extraction
memory.create_memory_and_wait(
    memory_id="mem-abc123",
    actor_id="user-u-123",
    session_id="sess-001",
    messages=[...],
)
```

## Namespaces

Namespaces isolate memory between users, sessions, or agent roles. The `{actorId}` and `{agentName}` template variables are resolved at runtime from verified identity claims and the blueprint:

```yaml
memory:
  strategies:
    - type: SEMANTIC
      name: "user-memory"
      namespace: "user/{actorId}/agent/{agentName}"
```

Each strategy takes a single `namespace` string field (not a list of namespaces).

## Multi-Namespace Retrieval

Configure multiple retrieval namespaces with independent `top_k` and relevance thresholds:

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

Results from each namespace are merged before injection.

## `MemoryBranchManager`

Wraps `bedrock_agentcore.memory.MemorySessionManager` to provide isolated memory contexts for sub-agents:

```python
from agent_core.memory.branching import MemoryBranchManager

branch_mgr = MemoryBranchManager(memory_id="mem-abc123")

session = branch_mgr.create_session(actor_id="coordinator", session_id="sess-1")

branch_mgr.fork_conversation(
    session=session,
    root_event_id="evt-000",
    branch_name="summarization-task",
    messages=[("Summarize the document.", "user")],
)

turns = branch_mgr.get_branch_turns(session, branch_name="summarization-task", k=10)
branches = branch_mgr.list_branches(session)
```

## `MemoryToolProvider`

When `memory.enable_tool_provider: true` is set in the blueprint, `MemoryToolProvider` exposes `memory_recall` and `memory_record` as tools the agent can invoke directly — in addition to the automatic hook-based persistence:

```python
from agent_core.memory.tool_provider import MemoryToolProvider

tool_provider = MemoryToolProvider(
    memory_id="mem-abc123",
    actor_id="agent-1",
    session_id="sess-001",
)

tools = tool_provider.get_tool_provider_tools()
agent = Agent(model=model, tools=[*other_tools, *tools])
```

Blueprint flag:

```yaml
memory:
  enable_tool_provider: false   # default; set true to add memory_recall / memory_record tools
```

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
  short_term_k: 5              # Number of recent turns to inject at session start
  enable_tool_provider: false
  retrieval:
    - namespace: "user/{actorId}"
      top_k: 10
      relevance_score: 0.3
```

`memory_id` is **not** a blueprint field. It is resolved at runtime from `AGENTCORE_MEMORY_ID`. This env var is injected by the platform Terraform via the `memory_id` output from the `agentcore` sub-module.

## See Also

- [Runtime & Memory guide](../runtime.md) — Memory architecture, strategy extraction timing
- [A2A SDK reference](a2a.md) — `MemoryBranchManager` in multi-agent coordination

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

## Hook Wiring

`MemoryHookProvider` is a plain `@dataclass` that implements the Strands `HookProvider` interface. It is constructed and injected by `MemoryWiring`, which is called automatically by `BlueprintLoader._wire_memory()`. Domain developers declare strategies in the blueprint YAML — no subclassing or manual hook instantiation is required.

For direct use outside the blueprint-driven path, construct via `MemoryWiring`:

```python
from agent_core.memory.wiring import MemoryWiring
from agent_core.schemas.memory_config import MemoryConfig, MemoryStrategyConfig

config = MemoryConfig(
    strategies=[
        MemoryStrategyConfig(
            type="SEMANTIC",
            name="semantic-extraction",
            namespace="user/{actorId}",
        )
    ],
    short_term_k=5,
    event_expiry_days=30,
)
wiring = MemoryWiring(config=config, memory_id="mem-abc123")
hook = wiring.hook_provider

agent = Agent(model=model, tools=tools, hooks=[hook])
```

The hook responds to two Strands lifecycle events:

**`AgentInitializedEvent`** — Fires when the agent starts. The hook:
1. Loads the last `short_term_k` turns from short-term storage
2. Runs semantic retrieval across all configured `retrieval` namespaces using the last user message as the query
3. Injects both as a `<memory_context>` block appended to `agent.system_prompt`

**`MessageAddedEvent`** — Fires after each conversation turn. The hook persists the turn via `create_event()`. Failures are logged and never propagate to the agent invocation.

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
