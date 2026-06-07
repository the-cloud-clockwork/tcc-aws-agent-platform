---
title: Memory
nav_order: 2
parent: "Runtime & Memory"
---

# Memory

AgentCore Memory solves the stateless microVM problem: when a session ends, the microVM is destroyed and all in-process state is gone. Memory provides managed storage **outside** the microVM so agents can accumulate knowledge across sessions.

## Two Storage Tiers

Memory has two tiers that serve distinct purposes:

```
                Short-Term (Events)                Long-Term (Strategies)
                +------------------+               +----------------------+
create_event()->| Raw turn buffer  |--async ~30s-->| Strategy extraction  |
                | TTL: 1–365 days  |               | pgvector embeddings  |
                | short_term_k: 5  |               | Semantic retrieval   |
                +------------------+               +----------------------+
```

### Short-Term Memory — Event Store

Raw conversation turn storage. Push conversation turns in; pull the last K turns back out. This is a time-ordered buffer — useful for resuming a conversation across sessions, but it does not interpret or learn from the content.

- Written synchronously on every `MessageAddedEvent`
- Retrieved at agent initialization (`AgentInitializedEvent`) and injected into the system prompt as `<memory_context>`
- Configurable TTL (1–365 days, default 30)
- Configurable retrieval window via `short_term_k` (default 5 turns)

### Long-Term Memory — Strategy Extraction

When you configure **strategies**, the system asynchronously processes raw events and extracts structured knowledge — user preferences, named facts, summaries, episodic memories. Extracted data is stored with vector embeddings and retrieved via semantic similarity search.

Strategy extraction is **asynchronous** (~30 seconds after events are written). The extracted data persists independently of the raw event TTL — so even after short-term events expire, the distilled knowledge remains.

## Strategy Types

| Strategy | What it extracts | Typical namespace pattern |
|----------|-----------------|--------------------------|
| `USER_PREFERENCE` | Stated preferences, behavioral patterns, explicit settings | `user/{actorId}/preferences/` |
| `SEMANTIC` | Named facts and entities about the actor | `user/{actorId}/facts/` |
| `SUMMARY` | Condensed summaries of conversation sessions | `user/{actorId}/{sessionId}/summaries/` |
| `EPISODIC` | Specific events or interactions worth remembering | `user/{actorId}/episodes/` |

`SUMMARIZATION` is accepted as an alias for `SUMMARY` in YAML blueprints (normalized by a field validator).

## Blueprint Configuration

Memory wires automatically when `strategies` is non-empty. The `AGENTCORE_MEMORY_ID` environment variable must be set at runtime — the loader raises `BlueprintLoadError` if it is absent when strategies are declared. There is no `memory_id` field in the blueprint YAML; the ID comes from the environment.

```yaml
memory:
  strategies:
    - type: USER_PREFERENCE
      name: PreferenceLearner
      namespace: "user/{actorId}/preferences/"
    - type: SEMANTIC
      name: FactExtractor
      namespace: "user/{actorId}/facts/"
    - type: SUMMARY
      name: Summarizer
      namespace: "user/{actorId}/{sessionId}/summaries/"
  event_expiry_days: 30   # 1–365 days; default 30
  short_term_k: 5         # turns loaded at agent init; default 5
  enable_tool_provider: false  # expose memory_recall / memory_record as agent tools
  retrieval:
    - namespace: "user/{actorId}/preferences/"
      top_k: 5
      relevance_score: 0.5
    - namespace: "user/{actorId}/facts/"
      top_k: 10
      relevance_score: 0.3
```

`{actorId}` and `{sessionId}` are resolved at runtime from the agent's state dict. This ensures memory from one user never leaks to another.

## How the Hook Wires In

`MemoryHookProvider` is a Strands `HookProvider` dataclass created and injected by `MemoryWiring` — which is called automatically by `BlueprintLoader._wire_memory()`. Domain developers declare strategies in the blueprint YAML; no subclassing or manual hook instantiation is required.

The hook registers callbacks for two Strands lifecycle events:

**`AgentInitializedEvent`** — Fires when the agent starts a session:
1. Loads the last `short_term_k` turns from the event store
2. Runs semantic retrieval across all configured `retrieval` namespaces
3. Injects both as a `<memory_context>` block appended to the system prompt

**`MessageAddedEvent`** — Fires after each conversation turn:
1. Extracts the text content from the last message
2. Calls `create_event()` to persist the turn to short-term storage

Both operations are fault-tolerant — exceptions are logged but never propagate to the agent invocation.

### Direct Use

For cases requiring explicit control outside the blueprint wiring:

```python
from agent_core.memory.manager import MemoryManager

memory = MemoryManager(memory_id="mem-abc123")

# Store conversation turns
memory.create_event(
    memory_id="mem-abc123",
    actor_id="user-u-123",
    session_id="sess-001",
    messages=[("What is the account balance?", "user"), ("$1,250.00", "assistant")],
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
    namespace="user/u-123/preferences/",
    query="communication style preferences",
    top_k=5,
)
```

## Agent-Callable Memory Tools

When `enable_tool_provider: true` is set, `MemoryToolProvider` exposes `memory_recall` and `memory_record` as Strands tools the agent can invoke directly — supplementing (not replacing) the automatic hook-based persistence. Wire the tools into the agent's tool list via `get_tool_provider_tools()` from `MemoryWiring`.

```python
from agent_core.memory.tool_provider import MemoryToolProvider

tool_provider = MemoryToolProvider(
    memory_id="mem-abc123",
    actor_id="user-1",
    session_id="sess-001",
)

agent = Agent(model=model, tools=[*other_tools, *tool_provider.tools])
```

## When to Use Each Tier

| Use case | Tier | Reason |
|----------|------|--------|
| Resume conversation from last turn | Short-term | Direct turn retrieval, no extraction delay |
| Remember user preferences across sessions | Long-term (`USER_PREFERENCE`) | Semantic extraction and retrieval |
| Build a knowledge base about a user | Long-term (`SEMANTIC`) | Entity and fact extraction |
| Summarize a long session for future reference | Long-term (`SUMMARY`) | Condensed, retrievable summary |
| Debug — replay a conversation | Short-term | Raw events in chronological order |
| Multi-agent context isolation | Branching | Fork/merge without state collision |

## Memory Branching in Multi-Agent Pipelines

In multi-agent setups, different agents sharing a memory resource need isolated write contexts. Branching prevents state collision:

```
Coordinator writes to "main" branch
    |
    +-- Specialist A forks → writes to "specialist-a" branch
    +-- Specialist B forks → writes to "specialist-b" branch
    |
Coordinator reads from any branch
```

```python
from bedrock_agentcore.memory import MemorySessionManager

manager = MemorySessionManager(memory_id="mem-abc123", region_name="us-west-2")
session = manager.create_memory_session(actor_id, session_id)

# Coordinator writes to main
session.add_turns(messages, branch={"name": "main"})

# Specialist forks from a coordinator event
session.fork_conversation(
    root_event_id=coordinator_event_id,
    branch_name="extraction-specialist",
)

# Coordinator reads specialist's output
specialist_context = session.get_last_k_turns(
    k=5,
    branch_name="extraction-specialist",
)
```

For the `MemoryBranchManager` wrapper API (`create_session`, `fork_conversation`, `get_branch_turns`, `list_branches`), see the [Memory SDK Reference](../sdk/memory).

## Event TTL and Long-Term Durability

Short-term events expire per `event_expiry_days`. Long-term strategy-extracted memories persist **independently** of the raw event TTL — the extraction is a separate record in pgvector storage. Increasing event TTL extends how long raw turns are available for replay and debugging; it does not affect the durability of extracted long-term memories.

## See Also

- [Memory SDK Reference](../sdk/memory) — `MemoryManager`, `MemoryHookProvider`, `MemoryBranchManager`, `MemoryToolProvider`
- [A2A Communication](a2a) — memory branching in coordinator/specialist pipelines
- [Agent Blueprint — `memory` block](../blueprints/agent-blueprint) — full schema reference
