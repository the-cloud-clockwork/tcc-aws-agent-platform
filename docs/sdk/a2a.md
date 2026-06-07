---
title: Agent-to-Agent
nav_order: 9
parent: SDK Reference
---

# Agent-to-Agent (A2A)

The A2A subsystem implements the [Agent-to-Agent protocol](https://google.github.io/A2A/), an open standard for inter-agent communication. It lets agents discover each other, negotiate capabilities, and delegate work — all over a standardized HTTP API secured with M2M auth.

> **Architecture guide:** [Runtime & Memory](../runtime.md)

## Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `A2AServerWrapper` | `agent_core.a2a.server` | Exposes your agent as an A2A server; serves agent card from blueprint |
| `A2AClient` | `agent_core.a2a.client` | Client for calling remote A2A agents (A2A protocol and direct invoke) |
| `A2AWiring` | `agent_core.a2a` | Wires remote agents as Strands `@tool` functions |

## Agent Cards

Every A2A agent publishes a machine-readable agent card at:

```
GET /.well-known/agent.json
```

`A2AServerWrapper` generates and serves this card automatically from the blueprint metadata (name, version, declared tools). `A2AClient.resolve_agent_card()` fetches this path.

> **Path is `agent.json`, not `agent-card.json`.** Both the server and client use `/.well-known/agent.json`.

## `A2AServerWrapper`

```python
class A2AServerWrapper:
    def __init__(
        self,
        agent: Agent,
        blueprint: AgentBlueprint,
        *,
        serve_at_root: bool = True,   # Required for AgentCore deployment
    ) -> None: ...

    @classmethod
    def from_blueprint(
        cls,
        loader: BlueprintLoader,
        agent_id: str,
    ) -> A2AServerWrapper: ...

    def to_starlette_app(self) -> Any:
        """Return the ASGI app for composition with the AgentCoreApp runtime."""
        ...

    def serve(self, port: int | None = None) -> None:
        """Serve standalone (blocking). Port from runtime.a2a_port or A2A_PORT env var."""
        ...
```

The A2A port resolves from `blueprint.runtime.a2a_port`, then the `A2A_PORT` env var. Raises `ValueError` if port resolves to 0.

In the standard blueprint-driven pattern, `loader.build_entrypoint()` calls `A2AServerWrapper.from_blueprint()` and mounts the app automatically when `blueprint.multi_agent.role == 'specialist'`. No manual setup is needed.

## `A2AClient`

```python
class A2AClient:
    def __init__(
        self,
        region: str | None = None,
        auth_token: str | None = None,
    ) -> None: ...

    def resolve_agent_card(self, url: str) -> dict:
        """Fetch /.well-known/agent.json from the remote agent."""
        ...

    def call_a2a(self, url: str, message: str, **kwargs) -> str:
        """Non-streaming call via JSON-RPC method 'message/send'."""
        ...

    def stream_a2a(self, url: str, message: str, **kwargs) -> Iterator[str]:
        """Streaming call via JSON-RPC method 'message/stream' (SSE)."""
        ...

    async def stream_a2a_async(self, url: str, message: str, **kwargs) -> AsyncIterator[str]:
        """Async streaming call."""
        ...

    def call_direct(
        self,
        runtime_arn: str,
        payload: dict,
    ) -> dict:
        """Bypass the A2A protocol — invoke directly via boto3 invoke_agent_runtime().
        Useful for tightly coupled agents within the same AWS account."""
        ...
```

## Coordinator / Specialist Pattern

**Specialist side** — the specialist blueprint declares its role; `build_entrypoint()` auto-mounts the A2A server:

```yaml
# specialist.yaml
id: summarization-agent
multi_agent:
  role: specialist
runtime:
  a2a_port: 9000
```

**Coordinator side** — use `A2AWiring` to register specialists as Strands tools:

```python
from agent_core.a2a import A2AWiring

wiring = A2AWiring.from_blueprint("coordinator.yaml")

# Discovers each specialist's agent card and wraps it as a Strands tool
tools = await wiring.get_remote_agent_tools()

coordinator = Agent(
    model=model,
    tools=[*local_tools, *tools],
)
```

Or use `remote_agent_tool()` for manual wiring:

```python
from agent_core.a2a.tools import remote_agent_tool
from agent_core.a2a.client import A2AClient

tool = remote_agent_tool(
    node_id="summarizer",
    name="summarize",
    description="Summarize a document",
    a2a_client=A2AClient(),
    a2a_url="https://summarizer.internal",
)
```

## Direct Invoke vs. A2A Protocol

| Method | When to Use |
|--------|-------------|
| `A2AClient.call_a2a()` / `stream_a2a()` | Standard A2A protocol — different accounts, external agents, any provider |
| `A2AClient.call_direct()` | Same-account, same-region tightly coupled agents — lower overhead, no A2A negotiation |

`call_direct()` uses the `boto3` `bedrock-agentcore` client with `invoke_agent_runtime()`. It bypasses the A2A protocol entirely.

## M2M Auth Flow

A2A communication uses M2M OAuth (client credentials grant). The [Identity subsystem](identity.md) handles token acquisition and injection. Configure the M2M credential provider in the blueprint and `A2AWiring` uses it automatically:

```yaml
identity:
  credentials:
    - name: m2m-internal
      type: oauth2
      auth_flow: M2M
      provider: coordinator-m2m-provider
      scopes: ["agent.invoke"]
```

## Blueprint Configuration

```yaml
# coordinator — orchestrates specialists
id: coordinator-agent
multi_agent:
  role: coordinator
  pattern: graph
  nodes:
    - node_id: summarizer
      agent_ref: summarization-agent
      a2a_url: "${SUMMARIZER_URL}"
    - node_id: extractor
      agent_ref: extraction-agent
      a2a_url_env: EXTRACTOR_URL      # Resolved from env var at runtime

# Remote nodes can also use direct AgentCore Runtime ARN invocation
    - node_id: classifier
      agent_ref: classifier-agent
      runtime_arn: "${CLASSIFIER_RUNTIME_ARN}"
```

```yaml
# specialist — callable by coordinator
id: summarization-agent
multi_agent:
  role: specialist
runtime:
  a2a_port: 9000
```

## See Also

- [Runtime & Memory guide](../runtime.md) — Multi-agent topologies, coordinator/specialist wiring
- [Identity SDK reference](identity.md) — M2M credential providers

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

**Coordinator side** — use `A2AWiring` to build remote tools from the blueprint's `multi_agent.nodes`:

```python
from agent_core.a2a.wiring import A2AWiring

# A2AWiring takes a loaded blueprint (not a file path)
wiring = A2AWiring(blueprint=coordinator_blueprint)

# Builds a @tool function for each remote node declared in multi_agent.nodes
remote_tools = wiring.build_remote_tools()

coordinator = Agent(
    model=model,
    tools=[*local_tools, *remote_tools],  # Mix local and remote tools
)
```

`A2AWiring.__init__` accepts a loaded `AgentBlueprint` and an optional `identity_wiring` for M2M auth. For coordinator roles it creates an `A2AClient`; `build_remote_tools()` iterates `multi_agent.nodes` and returns a Strands `@tool` function per node. Each tool resolves the remote agent's URL from the node's `a2a_url` / `a2a_url_env` field.

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
