---
title: Gateway
nav_order: 2
---

# Gateway

The Gateway subsystem provides a unified client for Amazon Bedrock AgentCore Gateway. Agents consume the Gateway as a single MCP endpoint — all tools registered as Gateway targets appear as MCP tools via one connection.

> **Note:** Gateway creation and target registration are handled automatically by the platform from blueprint YAML. The `GatewayClient` is a consumption-side client that agents use to discover and invoke tools at runtime.

## Key Classes

| Class | Purpose |
|-------|---------|
| `GatewayClient` | Strands MCPClient wrapper — discovers tools, manages auth, context-manager lifecycle |
| `TargetRegistry` | Tracks available Gateway targets and their tool manifests |
| `ToolDiscovery` | Semantic search over registered tools across all targets |

## Target Types

| Type | Use Case | Auth |
|------|----------|------|
| `LAMBDA` | AWS Lambda functions | IAM SigV4 |
| `MCP` | MCP servers (Streamable HTTP) | API key, OAuth, or none |
| `REST` | Generic HTTP APIs | API key or OAuth |
| `OPENAPI` | APIs described by an OpenAPI spec | API key or OAuth |
| `SMITHY` | Smithy-modeled services | IAM SigV4 |
| `API_GATEWAY` | Amazon API Gateway endpoints | IAM SigV4 or API key |

## Two Auth Layers

Gateway enforces authentication at two points:

1. **Agent to Gateway**: The agent must authenticate to the Gateway endpoint itself. This is typically IAM-based (SigV4) when running inside AWS, or JWT-based for external callers.

2. **Gateway to Target**: The Gateway authenticates to each backend target on the agent's behalf. Credentials are stored in Secrets Manager and resolved at invocation time.

The `GatewayClient` handles both layers automatically when configured from a blueprint.

## Three Auth Modes

| Mode | Transport | Use Case |
|------|-----------|----------|
| `aws_iam` | SigV4 via `streamable_http_sigv4` | Agents running inside AWS (default) |
| `custom_jwt` | Bearer token in `Authorization` header | External callers, cross-account |
| `none` | No auth | Local development only |

## Basic Usage

```python
from agent_core.gateway import GatewayClient
from strands import Agent

client = GatewayClient(gateway_url="https://gw.example.com/mcp")

with client:
    tools = client.list_tools_sync()
    agent = Agent(tools=[local_tool] + tools)
    result = agent("What orders are pending?")
```

## Strands Tool Provider Pattern

The most common pattern is to expose Gateway targets as tools to the Strands agent. `GatewayClient.as_tool_provider()` returns the underlying Strands `MCPClient`:

```python
from agent_core.gateway import GatewayClient
from strands import Agent

client = GatewayClient.from_config(blueprint.gateway)

# Returns a Strands MCPClient pointed at the Gateway's MCP endpoint
tool_provider = client.as_tool_provider()

agent = Agent(
    model=model,
    tools=[tool_provider],
)
```

All tools registered in the Gateway become available to the Strands agent without any additional wiring.

## Context Manager

`GatewayClient` supports the context manager protocol. Use it to ensure the underlying MCP transport is properly closed:

```python
with GatewayClient(gateway_url="https://gw.example.com/mcp") as client:
    tools = client.list_tools_sync()
    # ... use tools
# Transport is closed automatically
```

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

Gateway resources (the Gateway itself, targets, and their auth configurations) are declared in blueprint YAML and provisioned by the platform's Terraform modules. Agents reference the Gateway at runtime:

```yaml
gateway:
  url: "${AGENTCORE_GATEWAY_URL}"
  auth_type: aws_iam
  region: "${AWS_REGION}"
  service_name: bedrock-agentcore
```

The `AGENTCORE_GATEWAY_URL` environment variable is injected by the platform into the agent's runtime container.

## Error Handling

`GatewayClient` raises typed exceptions for common failure modes:

```python
from agent_core.gateway import GatewayError, GatewayPolicyDeniedError, GatewayConfigError

try:
    with client:
        tools = client.list_tools_sync()
except GatewayPolicyDeniedError as e:
    # Cedar policy denied tool access
    print(f"Denied: {e.tool_name} for agent {e.agent_id}")
except GatewayConfigError:
    # Missing URL, region, or JWT configuration
    pass
except GatewayError:
    # General gateway failure
    pass
```
