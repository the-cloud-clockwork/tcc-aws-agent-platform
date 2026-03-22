---
title: Agent-to-Agent
nav_order: 9
---

# Agent-to-Agent (A2A)

The A2A subsystem implements the [Agent-to-Agent protocol](https://google.github.io/A2A/), an open standard for inter-agent communication. It lets agents discover each other, negotiate capabilities, and delegate work — all over a standardized HTTP API secured with M2M auth.

## Key Classes

| Class | Purpose |
|-------|---------|
| `A2AServerWrapper` | Exposes your agent as an A2A server on port 9000 |
| `A2AClient` | Client for calling remote A2A agents |
| `A2AWiring` | Wires remote agents as Strands `@tool` functions |

## Agent Cards

Every A2A agent publishes a machine-readable agent card at a well-known URL:

```
GET /.well-known/agent-card.json
```

The card describes the agent's capabilities, input/output schemas, and auth requirements:

```json
{
  "name": "summarization-agent",
  "version": "1.0",
  "description": "Summarizes long documents into structured briefs",
  "capabilities": [
    {
      "name": "summarize",
      "description": "Summarize a document given its text or S3 URI",
      "input_schema": { "type": "object", "properties": { "text": { "type": "string" } } },
      "output_schema": { "type": "object", "properties": { "summary": { "type": "string" } } }
    }
  ],
  "auth": {
    "type": "bearer",
    "token_url": "https://auth.example.com/token"
  }
}
```

`A2AServerWrapper` generates and serves this card automatically from the agent blueprint.

## A2A Server Setup

Wrap an existing `AgentCoreApp` to add A2A capability:

```python
from agent_core.a2a import A2AServerWrapper

# Your standard runtime app
app = AgentCoreApp.from_blueprint("agent.yaml")

# Expose it on port 9000 (alongside /invocations on 8080)
a2a_server = A2AServerWrapper(app)
a2a_server.start(port=9000)
```

`A2AServerWrapper` handles:
- Serving `/.well-known/agent-card.json`
- Parsing A2A task requests
- Routing capability invocations to the right agent entrypoint
- Streaming responses back in A2A's streaming event format
- M2M auth validation on inbound requests

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

The coordinator can then call `summarization-agent.summarize(text=...)` as if it were a local function. The A2A client handles authentication, serialization, and error handling transparently.

**Specialist side** — just run `A2AServerWrapper` as shown above. No coordinator-specific code required.

## Remote Agents as Strands Tools

`A2AWiring` converts each remote capability into a Strands `@tool` function:

```python
# This is what A2AWiring generates automatically:
@tool
async def summarize(text: str) -> dict:
    """Summarize a document given its text."""
    return await a2a_client.call(
        agent_url="https://summarization-agent.internal",
        capability="summarize",
        inputs={"text": text},
    )
```

The coordinator's LLM sees the tool with its original name and description from the remote agent card, so the coordinator can choose the right specialist without hardcoded routing logic.

## M2M Auth Flow

A2A communication uses M2M OAuth (client credentials grant):

1. Coordinator requests a token from the auth server using its client credentials
2. Token includes the specialist's audience in the `aud` claim
3. Coordinator attaches the token as `Authorization: Bearer <token>`
4. Specialist's `A2AServerWrapper` validates the token (issuer, audience, expiry)
5. If valid, the request is processed; otherwise `401 Unauthorized` is returned

The token exchange is handled by the [Identity subsystem](identity.md)'s M2M provider. Configure it in the blueprint and `A2AWiring` uses it automatically.

## A2AClient Direct Usage

For lower-level control, use `A2AClient` directly:

```python
from agent_core.a2a import A2AClient

client = A2AClient.from_blueprint("coordinator.yaml")

# Discover what the remote agent can do
card = await client.get_agent_card("https://specialist.internal")

# Call a capability
result = await client.call(
    agent_url="https://specialist.internal",
    capability="analyze",
    inputs={"document_id": "doc-456"},
)
print(result.outputs["analysis"])
```

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
