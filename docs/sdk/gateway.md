---
title: Gateway
nav_order: 2
parent: SDK Reference
---

# Gateway

The Gateway subsystem provides a unified client for Amazon Bedrock AgentCore Gateway. Agents consume the Gateway as a single MCP endpoint — all tools registered as Gateway targets appear as MCP tools via one connection.

> **Architecture guide:** [Tools, MCP & Gateway](../tools.md)

> **Note:** Gateway creation and target registration are handled automatically by the platform from blueprint YAML. `GatewayClient` is a consumption-side client that agents use to discover and invoke tools at runtime.

## Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `GatewayClient` | `agent_core.gateway.client` | Strands `MCPClient` wrapper — discovers tools, manages auth, context-manager lifecycle |
| `TargetRegistry` | `agent_core.gateway.target_registry` | Tracks available Gateway targets and their tool manifests |

## `GatewayClient`

```python
class GatewayClient:
    def __init__(
        self,
        gateway_url: str | None = None,   # Falls back to AGENTCORE_GATEWAY_URL env var
        auth_type: str = "aws_iam",        # "aws_iam" | "custom_jwt" | "none"
        jwt_env_var: str | None = None,    # Env var name holding the JWT (custom_jwt only)
        region: str | None = None,         # Falls back to AWS_DEFAULT_REGION / AWS_REGION
        service_name: str = "bedrock-agentcore",
    ) -> None: ...

    @classmethod
    def from_config(cls, config: GatewayConfig) -> GatewayClient:
        """Create from a GatewayConfig schema object (e.g. blueprint.gateway)."""
        ...

    def list_tools_sync(self) -> list[Any]:
        """Discover all tools exposed by the Gateway."""
        ...

    def as_tool_provider(self) -> MCPClient:
        """Return the underlying Strands MCPClient for direct use as a tool provider."""
        ...

    def __enter__(self) -> GatewayClient: ...
    def __exit__(self, *args) -> None: ...
    def close(self) -> None: ...
```

`GatewayClient` appends `/mcp` to the URL automatically if the URL does not already end with `/mcp`.

## Target Types

| YAML `type` value | Use Case |
|-------------------|----------|
| `lambda` | AWS Lambda functions |
| `mcp_server` | MCP servers (Streamable HTTP) |
| `openapi` | APIs described by an OpenAPI spec |
| `smithy` | Smithy-modeled services |
| `api_gateway` | Amazon API Gateway endpoints |

## Outbound Auth Types

| `OutboundAuthType` | Description |
|-------------------|-------------|
| `GATEWAY_IAM_ROLE` | Gateway uses its IAM role to sign requests to the target |
| `OAUTH2_CREDENTIAL` | Gateway uses a registered OAuth2 credential provider |
| `NONE` | No outbound auth |

## Inbound Auth Modes

| Mode | Transport | Use Case |
|------|-----------|----------|
| `aws_iam` | SigV4 via `mcp-proxy-for-aws` (fallback: bundled `streamable_http_sigv4`) | Agents inside AWS (default) |
| `custom_jwt` | Bearer token in `Authorization` header | External callers, cross-account |
| `none` | No auth | Local development only |

## Basic Usage

```python
from agent_core.gateway import GatewayClient
from strands import Agent

with GatewayClient(gateway_url="https://gw.example.com") as client:
    tools = client.list_tools_sync()
    agent = Agent(tools=tools)
    result = agent("What orders are pending?")
```

## Blueprint-Driven Pattern

```python
from agent_core.gateway import GatewayClient

# Build from blueprint schema
client = GatewayClient.from_config(blueprint.gateway)
tool_provider = client.as_tool_provider()   # Returns the underlying MCPClient

agent = Agent(model=model, tools=[tool_provider])
```

## Blueprint Configuration

```yaml
gateway:
  url: "${AGENTCORE_GATEWAY_URL}"
  auth_type: aws_iam               # aws_iam | custom_jwt | none
  region: "${AWS_REGION}"
  service_name: bedrock-agentcore  # Override only if using a non-standard signing name
```

`AGENTCORE_GATEWAY_URL` is injected automatically by the platform Terraform into the agent's runtime environment.

## Error Types

| Exception | Raised When |
|-----------|-------------|
| `GatewayPolicyDeniedError` | Cedar policy denied the tool call |
| `GatewayConfigError` | Missing URL, region, or JWT configuration |
| `GatewayError` | General gateway failure (base class) |

```python
from agent_core.gateway.client import GatewayError, GatewayPolicyDeniedError, GatewayConfigError

try:
    with GatewayClient.from_config(blueprint.gateway) as client:
        tools = client.list_tools_sync()
except GatewayPolicyDeniedError as e:
    print(f"Denied: {e.tool_name} for agent {e.agent_id}")
except GatewayConfigError:
    # Missing URL or auth config
    pass
```

## `TargetRegistry`

`TargetRegistry` is used at deploy time (not in agent runtime code) to register Gateway targets from a YAML file:

```python
from agent_core.gateway.target_registry import TargetRegistry

registry = TargetRegistry(
    gateway_id="${AGENTCORE_GATEWAY_ID}",  # Falls back to AGENTCORE_GATEWAY_ID env var
    region="eu-west-1",
)
targets = TargetRegistry.load_targets_from_file("gateway-targets.yaml")
results = registry.synchronize_all(targets)
print(f"Registered {results['registered_count']} / {len(targets)} targets")
```

Target YAML format (`gateway-targets.yaml`):

```yaml
gateway_id: "${AGENTCORE_GATEWAY_ID}"
targets:
  - name: order-tools           # "name" — not "id"
    type: lambda                # lowercase: lambda | mcp_server | openapi | smithy | api_gateway
    lambda_arn: "${ORDER_TOOLS_LAMBDA_ARN}"
    outbound_auth: gateway_iam_role   # lowercase: gateway_iam_role | oauth2_credential | none

  - name: analytics-mcp
    type: mcp_server
    endpoint_url: "${ANALYTICS_MCP_URL}"   # "endpoint_url" — not "endpoint"
    outbound_auth: oauth2_credential
    oauth2_credential_provider_id: "${ANALYTICS_OAUTH2_PROVIDER_ARN}"
    tool_schema_path: schemas/analytics-tools.json   # Optional: inline schema file
```

## See Also

- [Tools, MCP & Gateway](../tools.md) — Architecture, target registration patterns
- [Built-in Tools](tools.md) — Code Interpreter and Browser tool providers
- [MCP Base Classes](mcp.md) — Building domain MCP servers
