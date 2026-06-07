---
title: A2A Communication
nav_order: 3
parent: "Runtime & Memory"
---

# Agent-to-Agent Communication

A2A (Agent-to-Agent) is a standardized protocol that lets agents discover each other, negotiate capabilities, and exchange structured messages — without hardcoded ARNs, without custom adapters, and across framework boundaries.

## Why A2A, Not Direct Invocation

You can call one agent from another using a direct AWS API call:

```python
import boto3, json

@tool
def call_specialist(query: str) -> str:
    client = boto3.client("bedrock-agentcore")
    response = client.invoke_agent_runtime(
        agentRuntimeArn="${SPECIALIST_ARN}",
        qualifier="DEFAULT",
        payload=json.dumps({"prompt": query}),
    )
    return parse_response(response)
```

This works but has significant limitations:

- **Hardcoded ARNs** — every coordinator must know every specialist's ARN at build time
- **No capability negotiation** — you cannot discover what a specialist can do before calling it
- **Brittle** — if a specialist moves or its interface changes, every caller breaks
- **No standardized message format** — each agent pair invents its own protocol
- **Framework lock-in** — a Strands coordinator cannot easily call an ADK or LangGraph specialist

A2A solves these by establishing a standard protocol layer: agents publish what they can do, and coordinators discover and call them by capability, not by ARN.

The platform provides `A2AServerWrapper` and `A2AClient` that implement this protocol and integrate with blueprint-driven agent configuration. `A2AClient.call_direct()` is available as an alternative bypass path when A2A protocol overhead is unnecessary (see [Direct Invoke](#direct-invoke-alternative-path) below).

## Agent Cards

Every A2A-capable agent publishes an **agent card** at the following well-known URL:

```
GET /.well-known/agent.json
```

The card is a JSON document describing the agent's name, version, capabilities, and skills. `A2AServerWrapper` generates and serves this card automatically from blueprint metadata (name, version, and declared tool declarations).

Example agent card:

```json
{
  "name": "Document Extraction Specialist",
  "version": "1.0.0",
  "description": "Extracts structured data from documents",
  "url": "http://0.0.0.0:9000/",
  "capabilities": {
    "streaming": false,
    "pushNotifications": false
  },
  "skills": [
    { "id": "extract-mcp_extract_tables", "name": "extract_tables" },
    { "id": "extract-mcp_classify_document", "name": "classify_document" }
  ]
}
```

A coordinator fetches this card to understand what the specialist can do before sending any messages. `A2AClient.resolve_agent_card()` is LRU-cached per base URL to avoid repeated network round-trips.

## A2A Port Convention

A2A servers run on a **configurable port**, separate from the AgentCore Runtime's port 8080:

- **Port 8080** — `POST /invocations` contract for user-facing agent sessions
- **A2A port** — the A2A server for agent-to-agent communication (resolved from `runtime.a2a_port` in the blueprint, then the `A2A_PORT` env var)

Both can run simultaneously on the same container: port 8080 is served by the AgentCore SDK; the A2A server runs in a background daemon thread started by `AgentCoreApp.run()`.

If neither `runtime.a2a_port` nor `A2A_PORT` is set and `A2AServerWrapper` is instantiated, it raises `ValueError`. Choose a port that does not conflict with other services in your container (9000 is a common convention).

## Setting Up an A2A Server

For blueprint-driven agents with `multi_agent.role: specialist`, the loader auto-mounts the A2A server. No code changes in `app.py` are needed.

For manual setup or advanced cases:

```python
from agent_core.a2a.server import A2AServerWrapper
from strands import Agent

agent = Agent(model=model, tools=[extract_tables, classify_document])

# Create from blueprint — port resolved from blueprint.runtime.a2a_port or A2A_PORT
a2a = A2AServerWrapper.from_blueprint(agent=agent, blueprint=blueprint)

# Compose with the main AgentCoreApp
starlette_app = a2a.to_starlette_app()
app.mount_a2a(starlette_app, a2a.port)

app.run()  # Starts both servers
```

`A2AServerWrapper` handles:
- Serving `/.well-known/agent.json` with agent card built from blueprint metadata
- Parsing A2A JSON-RPC task requests
- Routing invocations to the Strands agent
- Streaming responses back in A2A's SSE event format
- Setting `serve_at_root=True` (required for AgentCore Runtime deployment)

## Coordinator / Specialist Pattern

The dominant pattern: a coordinator agent delegates subtasks to specialist agents.

```
User request
     |
Coordinator (port 8080)
     |
     +-- A2A call --> Specialist A (port 8080/9000)
     +-- A2A call --> Specialist B (port 8080/9000)
     |
Final synthesized answer --> User
```

**Specialist blueprint** — declare role and A2A port:

```yaml
# specialist-agent.yaml
runtime:
  a2a_port: 9000

multi_agent:
  role: specialist
```

**Coordinator** — call specialists as tools using `A2AClient`:

```python
from agent_core.a2a.client import A2AClient

client = A2AClient(auth_provider=lambda: get_m2m_token())

@tool
async def extract_document(document_url: str) -> str:
    """Extract structured data from a document."""
    return await asyncio.to_thread(
        client.call_a2a,
        os.environ["EXTRACTION_SPECIALIST_URL"],
        f"Extract all tables from: {document_url}",
    )
```

The coordinator does not know the specialist's implementation. It only needs the base URL.

## Calling Remote Agents

`A2AClient` provides three call patterns:

### Non-Streaming (`call_a2a`)

```python
from agent_core.a2a.client import A2AClient

client = A2AClient(auth_provider=lambda: get_m2m_token())

# Resolves agent card, sends JSON-RPC "message/send", returns text response
result = client.call_a2a(
    a2a_url="https://specialist.internal",
    message="Summarize this document",
)
```

### Streaming (`stream_a2a` / `stream_a2a_async`)

```python
# Synchronous streaming — yields text chunks via JSON-RPC "message/stream" + SSE
for chunk in client.stream_a2a("https://specialist.internal", "Analyze this data"):
    print(chunk, end="", flush=True)

# Async streaming
async for chunk in client.stream_a2a_async("https://specialist.internal", "Analyze"):
    print(chunk, end="", flush=True)
```

Both use the A2A `message/stream` JSON-RPC method with SSE transport.

## Direct Invoke — Alternative Path

For tightly coupled agents in the same AWS account where A2A protocol overhead is unnecessary, `A2AClient.call_direct()` invokes the remote runtime directly via the boto3 `bedrock-agentcore` client:

```python
response = client.call_direct(
    runtime_arn="arn:aws:bedrock-agentcore:us-west-2:123456789012:agent-runtime/rt-abc",
    payload={"prompt": "Summarize this document"},
)
```

This bypasses A2A protocol entirely. The tradeoff: no capability negotiation, no agent card discovery, and auth is handled by the IAM role on the calling agent rather than M2M OAuth tokens.

## M2M Authentication

When agents communicate across Runtimes, they use machine-to-machine OAuth (client credentials grant):

```
sequenceDiagram
    Coordinator ->> Auth Server: Request token (client_credentials flow)
    Auth Server  ->> Coordinator: Access token
    Coordinator  ->> Specialist:  GET /.well-known/agent.json (Bearer token)
    Specialist   ->> Specialist:  Validate token
    Specialist   ->> Coordinator: Agent card
    Coordinator  ->> Specialist:  JSON-RPC message (Bearer token)
    Specialist   ->> Coordinator: Response
```

`A2AClient` accepts an `auth_provider` callable that returns a Bearer token string. The platform's [Identity subsystem](../policy/identity) provides `@requires_access_token` for automated token acquisition and refresh within agent tools.

## Memory Branching in Multi-Agent Pipelines

When multiple agents in a pipeline share a Memory resource, branching prevents context collision. Each specialist writes to its own branch forked from the coordinator's event:

```python
from bedrock_agentcore.memory import MemorySessionManager

manager = MemorySessionManager(memory_id="mem-abc123", region_name="us-west-2")
session = manager.create_memory_session(actor_id, session_id)

# Coordinator writes to main
session.add_turns(messages, branch={"name": "main"})

# Each specialist writes to its own branch
session.fork_conversation(
    root_event_id=coordinator_event_id,
    branch_name="extraction-specialist",
)

# Coordinator reads back from specialist branch — no cross-contamination
specialist_context = session.get_last_k_turns(
    k=5, branch_name="extraction-specialist"
)
```

See [Memory — Branching](memory#memory-branching-in-multi-agent-pipelines) for the full `MemoryBranchManager` API.

## Cross-Framework Interoperability

A2A is a protocol standard, not tied to Strands. A Strands coordinator can call an ADK specialist; a LangGraph coordinator can call a Strands specialist. Any agent that implements the A2A protocol at `/.well-known/agent.json` and accepts `message/send` or `message/stream` JSON-RPC requests is compatible.

## See Also

- [A2A SDK Reference](../sdk/a2a) — `A2AServerWrapper`, `A2AClient`, `A2AWiring`, `remote_agent_tool()`
- [Identity — M2M Pattern](../policy/identity) — M2M OAuth token acquisition for inter-agent auth
- [Memory — Branching](memory#memory-branching-in-multi-agent-pipelines) — context isolation in coordinator/specialist pipelines
- [Agent Blueprint — `multi_agent` block](../blueprints/agent-blueprint) — role, graph nodes, remote agent config
