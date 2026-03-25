---
title: Memory
nav_order: 4
parent: Concepts
---

# Persistence Across Sessions

AgentCore Memory solves the stateless microVM problem: agents forget everything when a session ends. Memory provides managed storage *outside* the microVM so agents can accumulate knowledge over time.

## The Problem

AgentCore Runtime gives each session an isolated microVM. That isolation is valuable — no shared state between concurrent users, no security leakage. But it also means that when a session ends, everything is gone. If a user mentions their preferences in session 1, session 2 starts with no context.

Memory bridges this gap. It lives as a separate managed service outside the Runtime, persisting data through session boundaries.

## Two Tiers

Memory has two storage tiers that serve different purposes:

```
                Short-Term (Events)               Long-Term (Strategies)
                +-----------------+               +----------------------+
create_event()->| Raw turns        |--async ~30s-->| Semantic extraction  |
                | TTL: 7–365 days  |               | pgvector embeddings  |
                | get_last_k_turns |               | Namespaced retrieval |
                +-----------------+               +----------------------+
```

### Short-Term Memory (Events)

Raw conversation turn storage. You push conversation turns in and pull the last N turns back out. This is a time-ordered buffer — useful for continuing a conversation across sessions, but it does not interpret or learn from the content.

Use short-term memory to:
- Resume a conversation where it left off
- Provide recent context to a new session
- Build conversation replay for debugging

### Long-Term Memory (Strategy Extraction)

When you configure **strategies**, the system asynchronously processes raw events and extracts structured knowledge — user preferences, facts, summaries, episodic memories. This extracted data is stored with vector embeddings in pgvector and retrieved via semantic search.

Strategy extraction happens asynchronously (~30 seconds after events are written). The extracted data is more durable and more semantically rich than raw turns.

## Strategy Types

| Strategy | What It Extracts | Namespace Pattern |
|----------|-----------------|-------------------|
| `USER_PREFERENCE` | User preferences and behavioral patterns | `user/{actorId}/preferences/` |
| `SEMANTIC` | Named facts and entities about the user | `user/{actorId}/facts/` |
| `SUMMARY` | Condensed summaries of conversation sessions | `user/{actorId}/{sessionId}/summaries/` |
| `EPISODIC` | Specific events or interactions worth remembering | `user/{actorId}/episodes/` |

## Namespacing

Namespaces use `{actorId}` and `{sessionId}` placeholders that resolve at runtime. This provides fine-grained scoping:

- `user/{actorId}/preferences/` — per-user preferences, shared across all of that user's sessions
- `user/{actorId}/{sessionId}/summaries/` — per-session summaries, isolated per conversation

In the blueprint:

```yaml
memory:
  memory_id: ${MEMORY_ID}
  strategies:
    - type: user_preference
      name: PreferenceLearner
      namespaces:
        - "user/{actorId}/preferences/"
    - type: semantic
      name: FactExtractor
      namespaces:
        - "user/{actorId}/facts/"
    - type: summary
      name: Summarizer
      namespaces:
        - "user/{actorId}/{sessionId}/summaries/"
```

## How It Wires Into the Agent

The canonical pattern is a `HookProvider` — a Strands hook that loads history when the agent initializes and saves messages as they are added:

```python
class MemoryHookProvider(HookProvider):
    def on_agent_initialized(self, event):
        actor_id = event.agent.state.get("actor_id")
        session_id = event.agent.state.get("session_id")

        # Load short-term: last 5 turns from previous sessions
        turns = client.get_last_k_turns(
            memory_id=memory_id, actor_id=actor_id, session_id=session_id, k=5)

        # Load long-term: semantic retrieval of user preferences
        preferences = client.retrieve_memories(
            memory_id=memory_id,
            namespace=f"user/{actor_id}/preferences/",
            query="user preferences",
            top_k=5,
        )

        # Inject both into the system prompt
        if turns or preferences:
            event.agent.system_prompt += f"\n\nRecent history:\n{format_turns(turns)}"
            event.agent.system_prompt += f"\n\nKnown preferences:\n{format_memories(preferences)}"

    def on_message_added(self, event):
        last = event.agent.messages[-1]
        client.create_event(
            memory_id=memory_id,
            actor_id=event.agent.state["actor_id"],
            session_id=event.agent.state["session_id"],
            messages=[(last["content"][0]["text"], last["role"])],
        )
```

This hook is declared in the blueprint via `memory.hook_provider` and wired automatically by `AgentCoreApp.from_blueprint()`.

## Memory Branching in Multi-Agent Pipelines

In multi-agent setups, different agents in a pipeline need to share memory without overwriting each other's context. Memory branching solves this:

```
Coordinator writes to "main" branch
    |
    +-- Sub-agent A forks → writes to "sub-agent-a" branch
    +-- Sub-agent B forks → writes to "sub-agent-b" branch
    |
Coordinator reads from any branch
```

```python
from bedrock_agentcore.memory import MemorySessionManager

manager = MemorySessionManager(memory_id=memory_id, region_name="${AWS_REGION}")
session = manager.create_memory_session(actor_id, session_id)

# Coordinator writes to main
session.add_turns(messages, branch={"name": "main"})

# Sub-agent forks from a specific event
session.fork_conversation(
    root_event_id=event_id,
    branch_name="extraction-agent"
)

# Coordinator reads from sub-agent's branch
sub_context = session.get_last_k_turns(k=5, branch_name="extraction-agent")
```

This pattern is useful for orchestrator/worker pipelines where the coordinator needs to read what each specialist agent produced without their outputs bleeding into each other's context.

## When to Use Each Tier

| Use Case | Tier | Reason |
|----------|------|--------|
| Resume a conversation from last turn | Short-term | Direct turn retrieval, no extraction delay |
| Remember user preferences across sessions | Long-term (USER_PREFERENCE) | Semantic extraction and retrieval |
| Build a knowledge base about the user | Long-term (SEMANTIC) | Entity and fact extraction |
| Summarize a long session for future reference | Long-term (SUMMARY) | Condensed, retrievable summary |
| Debugging — replay a conversation | Short-term | Raw events in order |
| Multi-agent context isolation | Branching | Fork/merge without state collision |

## Event TTL

Short-term events have a configurable expiry (7–365 days). Long-term strategy-extracted data persists independently of the raw event TTL. Set the TTL based on your use case:

- High-frequency, ephemeral interactions: 7–30 days
- Long-term user relationships: 90–365 days

```yaml
memory:
  event_expiry_days: 30
```

## See Also

- [Memory SDK Reference](../sdk/) — `MemoryManager`, `MemoryHookProvider`, `MemoryBranchManager`
- [A2A Concepts](a2a) — memory branching in coordinator/specialist pipelines
- [Agent Blueprint](../blueprints/agent-blueprint) — `memory:` block configuration
