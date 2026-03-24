---
title: Agent-to-Agent
nav_order: 9
---

# Agent-to-Agent (A2A)

The A2A subsystem implements the [Agent-to-Agent protocol](https://google.github.io/A2A/), an open standard for inter-agent communication. It lets agents discover each other, negotiate capabilities, and delegate work — all over a standardized HTTP API secured with M2M auth.

## Key Classes

| Class | Purpose |
|-------|---------|
| `A2AServerWrapper` | Exposes your agent as an A2A server with auto-generated agent card from blueprint |
| `A2AClient` | Client for calling remote A2A agents (sync, streaming, and direct invoke) |
| `A2AWiring` | Wires remote agents as Strands `@tool` functions via `remote_agent_tool()` |

## Agent Cards

Every A2A agent publishes a machine-readable agent card at a well-known URL:

```
GET /.well-known/agent.json
```

The card describes the agent's capabilities, skills, and version. `A2AServerWrapper` generates and serves this card automatically from the agent blueprint metadata (name, version, declared tools).

## A2A Server Setup

Wrap a Strands agent to add A2A capability. `A2AServerWrapper` takes the agent and blueprint, builds skills from tool declarations, and returns a Starlette ASGI app:

```python
from agent_core.a2a.server import A2AServerWrapper

# Create wrapper from agent and blueprint
a2a = A2AServerWrapper(agent=agent, blueprint=blueprint)

# Get the Starlette app for composition with the main runtime
app = a2a.to_starlette_app()

# Or run standalone (blocking)
a2a.serve()
```

`A2AServerWrapper` handles:
- Serving `/.well-known/agent.json`
- Parsing A2A JSON-RPC task requests
- Routing invocations to the Strands agent
- Streaming responses back in A2A's streaming event format
- The A2A port is configured via `runtime.a2a_port` in the blueprint or `A2A_PORT` env var

## Coordinator/Specialist Pattern

The most common multi-agent topology: one coordinator agent delegates to specialist agents.

**Coordinator side** — use `A2AWiring` to register specialists as tools:

```python
from agent_core.a2a import A2AWiring

wiring = A2AWiring.from_blueprint("coordinator.yaml")

# Discovers each specialist's agent card and creates a Strands tool
tools = await wiring.get_remote_agent_tools()

coordinator = Agent(
    model=model,
    tools=[*local_tools, *tools],  # Mix local and remote tools
)
```

The coordinator can then call specialist agents as if they were local functions. The A2A client handles authentication, serialization, and error handling transparently.

**Specialist side** — just run `A2AServerWrapper` as shown above. No coordinator-specific code required.

## Remote Agents as Strands Tools

`remote_agent_tool()` from `agent_core.a2a.tools` converts a remote agent endpoint into a Strands `@tool` function:

```python
from agent_core.a2a.tools import remote_agent_tool
from agent_core.a2a.client import A2AClient

client = A2AClient()

tool = remote_agent_tool(
    node_id="summarizer",
    name="summarize",
    description="Summarize a document",
    a2a_client=client,
    a2a_url="https://summarizer.internal",
)

coordinator = Agent(model=model, tools=[tool])
```

The coordinator's LLM sees the tool with the configured name and description, so it can choose the right specialist without hardcoded routing logic.

## Direct Invoke (Alternative to A2A)

For cases where A2A protocol overhead is unnecessary, `A2AClient.call_direct()` invokes a remote agent runtime directly via the boto3 `bedrock-agentcore` client using `invoke_agent_runtime()`:

```python
from agent_core.a2a.client import A2AClient

client = A2AClient(region="us-west-2")

response = client.call_direct(
    runtime_arn="arn:aws:bedrock-agentcore:us-west-2:123456789012:agent-runtime/rt-abc",
    payload={"prompt": "Summarize this document"},
)
print(response)
```

This bypasses A2A protocol entirely and calls the AgentCore Runtime API directly. Useful for tightly coupled agents within the same AWS account.

## Streaming

`A2AClient` supports streaming responses via SSE (Server-Sent Events) using the A2A `message/stream` method:

```python
client = A2AClient()

# Synchronous streaming
for chunk in client.stream_a2a("https://specialist.internal", "Analyze this data"):
    print(chunk, end="")

# Async streaming
async for chunk in client.stream_a2a_async("https://specialist.internal", "Analyze this data"):
    print(chunk, end="")
```

## ADK Integration (RemoteA2aAgent)

For Google ADK interoperability, use `RemoteA2aAgent` from the ADK library to wrap A2A endpoints as ADK-compatible agent objects. This enables mixed Strands/ADK topologies where some agents run on AgentCore and others run on ADK infrastructure.

## M2M Auth Flow

A2A communication uses M2M OAuth (client credentials grant):

1. Coordinator requests a token from the auth server using its client credentials
2. Token includes the specialist's audience in the `aud` claim
3. Coordinator attaches the token as `Authorization: Bearer <token>`
4. Specialist's `A2AServerWrapper` validates the token (issuer, audience, expiry)
5. If valid, the request is processed; otherwise `401 Unauthorized` is returned

The token exchange is handled by the [Identity subsystem](identity.md)'s M2M provider. Configure it in the blueprint and `A2AWiring` uses it automatically.

## Blueprint Configuration

```yaml
# coordinator.yaml
a2a:
  server:
    enabled: false   # Coordinator does not need to be callable

  specialists:
    - name: summarization-agent
      url: "https://summarizer.internal"
      auth:
        provider: m2m-internal   # References identity.outbound[name=m2m-internal]
    - name: extraction-agent
      url: "https://extractor.internal"
      auth:
        provider: m2m-internal
```

```yaml
# specialist.yaml
a2a:
  server:
    enabled: true
    port: 9000
```
