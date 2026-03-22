---
title: Gateway
nav_order: 2
---

# Gateway

The Gateway subsystem provides a unified client for Amazon Bedrock AgentCore Gateway. It abstracts over four target types (Lambda, MCP, REST, OpenAPI) and handles the two-layer authentication model: agent-to-Gateway auth and Gateway-to-target auth.

## Key Classes

| Class | Purpose |
|-------|---------|
| `GatewayClient` | High-level client — discovers targets, invokes tools, manages auth tokens |
| `TargetRegistry` | Tracks available Gateway targets and their tool manifests |
| `ToolDiscovery` | Semantic search over registered tools across all targets |

## Target Types

| Type | Use Case | Auth |
|------|----------|------|
| `LAMBDA` | AWS Lambda functions | IAM SigV4 |
| `MCP` | MCP servers (SSE or HTTP) | API key, OAuth, or none |
| `REST` | Generic HTTP APIs | API key or OAuth |
| `OPENAPI` | APIs described by an OpenAPI spec | API key or OAuth |

## Two Auth Layers

Gateway enforces authentication at two points:

1. **Agent → Gateway**: The agent must authenticate to the Gateway endpoint itself. This is typically IAM-based (Sigv4) when running inside AWS, or JWT-based for external callers.

2. **Gateway → Target**: The Gateway authenticates to each backend target on the agent's behalf. Credentials are stored in Secrets Manager and resolved at invocation time.

The `GatewayClient` handles both layers automatically when configured from a blueprint.

## Basic Usage

```python
from agent_core.gateway import GatewayClient

client = GatewayClient.from_blueprint("agent.yaml")

# List all available targets
targets = await client.list_targets()

# Invoke a tool on a specific target
result = await client.invoke_tool(
    target_id="my-data-api",
    tool_name="search_records",
    parameters={"query": "recent activity", "limit": 10},
)
```

## Strands MCPClient Consumption

The most common pattern is to expose Gateway targets as tools to the Strands agent. `GatewayClient` produces a Strands-compatible `MCPClient` that the agent can use directly:

```python
from agent_core.gateway import GatewayClient
from strands import Agent

client = GatewayClient.from_blueprint("agent.yaml")

# Returns a Strands MCPClient pointed at the Gateway's MCP endpoint
mcp_client = client.as_mcp_client()

agent = Agent(
    model=model,
    tools=[mcp_client],
)
```

All tools registered in the Gateway become available to the Strands agent without any additional wiring.

## Semantic Tool Search

`ToolDiscovery` indexes tool names and descriptions across all registered targets and supports natural-language queries:

```python
from agent_core.gateway import ToolDiscovery

discovery = ToolDiscovery(client)

# Find tools relevant to a user intent
tools = await discovery.search("summarize documents and extract key points")
# Returns ranked list of tool descriptors from any target
```

Use this to dynamically select the right tool when the agent has many targets registered.

## Blueprint Configuration

```yaml
gateway:
  endpoint: "https://${GATEWAY_ID}.gateway.bedrock-agentcore.${AWS_REGION}.amazonaws.com"
  targets:
    - id: document-api
      type: REST
      endpoint: "https://api.example.com"
      auth:
        type: api_key
        secret_arn: "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:doc-api-key"
    - id: analysis-mcp
      type: MCP
      endpoint: "https://mcp.example.com/sse"
      auth:
        type: oauth2
        token_url: "https://auth.example.com/token"
```

## TargetRegistry

The `TargetRegistry` caches target metadata and tool manifests. It refreshes automatically when the Gateway reports a change, or you can force a refresh:

```python
registry = client.registry

# Force refresh of all target manifests
await registry.refresh()

# Get the tool manifest for a specific target
manifest = await registry.get_manifest("document-api")
for tool in manifest.tools:
    print(tool.name, tool.description)
```

## Error Handling

`GatewayClient` raises typed exceptions for common failure modes:

```python
from agent_core.gateway import TargetUnavailableError, ToolNotFoundError

try:
    result = await client.invoke_tool("my-target", "my-tool", {})
except TargetUnavailableError:
    # Target is unreachable or unhealthy
    pass
except ToolNotFoundError:
    # Tool name not found in target manifest
    pass
```
