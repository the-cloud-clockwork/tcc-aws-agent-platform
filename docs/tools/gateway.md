---
title: Gateway
nav_order: 1
parent: "Tools, MCP & Gateway"
---

# The Universal Tool Bridge

AgentCore Gateway is a managed protocol translator that makes any backend — Lambda functions, REST APIs, OpenAPI services, Smithy services, API Gateway endpoints, or MCP servers — accessible to agents through a single MCP interface.

## The Problem Gateway Solves

Agents need tools. Those tools live in many different places: Lambda functions, internal REST APIs, third-party OpenAPI services, other agent runtime MCP servers. Without Gateway, every agent needs custom adapter code for each backend. As tools and agents multiply, this becomes a maintenance burden and a security risk — every agent managing its own credentials to every backend.

Gateway eliminates this by acting as a **central hub**: every backend registers with Gateway once, and every agent connects to Gateway once. The agent speaks MCP to Gateway; Gateway speaks whatever the backend needs.

The key insight is that Gateway is not just an API proxy — it is a **protocol translator**. It generates typed MCP tool schemas from Lambda invocation specs, OpenAPI documents, Smithy models, or explicit inline definitions. Agents never know what is behind a tool.

## Where Gateway Sits

```
                        +-------------------------+
                        |   AgentCore Gateway      |
                        |   (single MCP endpoint)  |
                        |                          |
Agent -- MCP ---------->|  Lambda Target     ------|---- IAM Role ---- Lambda fn
                        |  MCP Server Target ------|---- MCP -------- Runtime MCP server
                        |  OpenAPI Target    ------|---- HTTP ------- OpenAPI service
                        |  Smithy Target     ------|---- HTTP ------- Smithy service
                        |  API Gateway Target ------|---- HTTP ------- API Gateway
                        +-------------------------+
```

The agent connects to one URL. Gateway routes tool calls to the appropriate backend, handles auth for each target, and returns results in MCP format.

## Five Target Types

| Type | YAML value | Use Case |
|------|-----------|----------|
| Lambda | `lambda` | AWS Lambda functions — tool schema defined inline |
| MCP Server | `mcp_server` | Runtime MCP servers (Streamable HTTP) |
| OpenAPI | `openapi` | APIs described by an OpenAPI spec |
| Smithy | `smithy` | Smithy-modeled services |
| API Gateway | `api_gateway` | Amazon API Gateway REST / HTTP endpoints |

These are the five values accepted by `TargetType` in the platform SDK. Use the lowercase YAML values shown above in your `gateway-targets.yaml` file.

## Two Auth Layers

Gateway enforces authentication at two independent points.

**Inbound auth — who can call the Gateway**

- `aws_iam` — callers sign requests with SigV4. Agents running on Runtime with the correct IAM role authenticate automatically.
- `custom_jwt` — callers present a JWT (typically from Cognito). This is how end-user identity flows: the user's Cognito token passes from the frontend through the agent to the Gateway, which validates it before routing any tool call.

**Outbound auth — how Gateway authenticates to its targets**

| Target Type | Auth Method | How It Works |
|-------------|-------------|--------------|
| Lambda | `GATEWAY_IAM_ROLE` | Gateway signs the invocation with IAM SigV4. No token exchange. |
| MCP Server (Runtime) | `OAUTH2_CREDENTIAL` | Gateway retrieves an M2M access token from an OAuth2 credential provider and injects it as a Bearer token. |
| OpenAPI / Smithy / API Gateway | `OAUTH2_CREDENTIAL` or `GATEWAY_IAM_ROLE` | OAuth2 for third-party APIs; IAM role for internal AWS services. |

This separation is architecturally important. An end user authenticates with their Cognito JWT (inbound), but the actual tool calls are made using the Gateway's own credentials (outbound). **The user's identity flows as context for policy evaluation — not as credentials for tool access.** This is delegation, not impersonation.

### M2M Token Flow for MCP Server Targets

When Gateway invokes an MCP server target that requires OAuth, it uses the `client_credentials` grant to obtain an M2M access token. The platform provisions a Cognito Resource Server with custom scopes and a confidential M2M client. Gateway calls `GetResourceOauth2Token` on the credential provider, which handles the token exchange with the Cognito token endpoint. The resulting Bearer token is injected into the request to the MCP Runtime. On the receiving side, the Runtime validates the token using a JWT authorizer configured with the Cognito OIDC discovery URL.

```
Agent ──MCP──> Gateway ──GetResourceOauth2Token──> Cognito Token Endpoint
                  │                                          │
                  │       Bearer token (M2M)                 │
                  │<─────────────────────────────────────────┘
                  │
                  └──Bearer──> MCP Runtime (JWT authorizer validates)
```

For Lambda targets the flow is simpler — no token exchange is needed. Gateway signs the Lambda invocation with its IAM role using SigV4 directly.

## Protocol Translation — Lambda to MCP

When you register a Lambda function as a Gateway target, you provide the tool schema inline or via a JSON file. Gateway maps each tool name to a Lambda invocation.

The `gateway-targets.yaml` file (owned by the domain repo) declares targets:

```yaml
gateway_id: "${AGENTCORE_GATEWAY_ID}"
targets:
  - name: order-tools
    type: lambda
    lambda_arn: "${ORDER_TOOLS_LAMBDA_ARN}"
    outbound_auth: gateway_iam_role
    tool_schema_path: schemas/order-tools.json

  - name: analytics-mcp
    type: mcp_server
    endpoint_url: "${ANALYTICS_MCP_URL}"
    outbound_auth: oauth2_credential
    oauth2_credential_provider_id: "${ANALYTICS_OAUTH2_PROVIDER_ID}"
```

Key fields in each target entry:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Unique target name; becomes tool namespace prefix |
| `type` | yes | One of: `lambda`, `mcp_server`, `openapi`, `smithy`, `api_gateway` |
| `lambda_arn` | for lambda | Lambda function ARN |
| `endpoint_url` | for non-lambda | URL of the remote service |
| `tool_schema_path` | optional | Path to a JSON file describing tool schemas (for Lambda/OpenAPI) |
| `outbound_auth` | optional | `gateway_iam_role` (default) or `oauth2_credential` |
| `oauth2_credential_provider_id` | for OAuth2 | ARN of the credential provider resource |

The platform uses `TargetRegistry.load_targets_from_file()` to load this file and register targets with the Gateway via the `bedrock-agentcore-control` API.

When the agent calls a tool, the chain is:

```
Strands agent → MCPClient → Gateway → Lambda({"orderId": "123"}) → response
```

The agent has no idea it is calling Lambda. It sees the tool as a regular MCP tool.

## Protocol Translation — OpenAPI and Smithy

For OpenAPI services, Gateway derives tool schemas automatically from the spec — no manual schema definition required. Pass the `tool_schema_path` pointing to your OpenAPI document, or provide `endpoint_url` alone if the service serves its spec at a standard path.

Smithy targets use the Smithy service model to generate MCP interfaces. Provide `endpoint_url` with `type: smithy`.

## Consuming Gateway Tools in an Agent

`GatewayClient` from `agent-core` wraps a Strands `MCPClient` pointed at the Gateway's MCP endpoint. The recommended construction is from a `GatewayConfig`:

```python
from agent_core.gateway import GatewayClient
from strands import Agent

# From blueprint config (preferred)
client = GatewayClient.from_config(blueprint.gateway)

# Or directly
client = GatewayClient(
    gateway_url="https://${GATEWAY_ID}.gateway.bedrock-agentcore.${AWS_REGION}.amazonaws.com",
    auth_type="aws_iam",
    region="eu-west-1",
)

with client:
    gateway_tools = client.list_tools_sync()
    agent = Agent(model=model, tools=local_tools + gateway_tools)
```

`GatewayClient.as_tool_provider()` returns the underlying Strands `MCPClient` for use directly as a tool provider:

```python
tool_provider = client.as_tool_provider()
agent = Agent(model=model, tools=[tool_provider])
```

All tools from all registered targets are exposed through this single client. The agent mixes local tools and remote Gateway tools without distinction.

### URL Auto-Correction

`GatewayClient` automatically appends `/mcp` to the Gateway URL if it does not already end with `/mcp`. You can provide the base Gateway URL without worrying about the path suffix.

### SigV4 Transport

The `aws_iam` mode uses `mcp-proxy-for-aws` (`aws_iam_streamablehttp_client`) when installed, which handles container credential resolution correctly inside AgentCore Runtime microVMs. It falls back to the bundled `streamable_http_sigv4` transport if that library is not installed.

Install the preferred transport with:

```bash
pip install mcp-proxy-for-aws
```

## Blueprint Configuration

The `gateway:` block in an agent blueprint configures the client:

```yaml
gateway:
  url: "${AGENTCORE_GATEWAY_URL}"   # Falls back to env var if omitted
  auth_type: aws_iam                # aws_iam | custom_jwt | none
  region: "${AWS_REGION}"
  service_name: bedrock-agentcore   # AWS service name for SigV4 signing
```

The `AGENTCORE_GATEWAY_URL` environment variable is injected by the platform into every agent Runtime container. The `service_name` field defaults to `bedrock-agentcore` and only needs to be overridden in non-standard deployments.

## MCP Aggregation Pattern

Gateway can front multiple MCP servers through a single URL. The agent connects to one Gateway endpoint and gets tools from all registered targets:

```
Agent -> Gateway (single URL) -> Runtime MCP Server A (data extraction tools)
                               -> Runtime MCP Server B (analysis tools)
                               -> Lambda Target C (utility tools)
```

The agent has no awareness that tools come from different backends. It calls `list_tools_sync()` once and gets a unified tool list from every registered target.

## Tool Discovery

`ToolDiscovery` enables semantic search across all registered targets. Useful when an agent has many tools and needs to dynamically select the relevant ones for a given task:

```python
from agent_core.gateway import ToolDiscovery

discovery = ToolDiscovery(client)
tools = await discovery.search("summarize documents and extract key findings")
# Returns ranked tool descriptors from any target
```

## Policy Engine Integration

Gateway has a built-in hook for attaching a Cedar policy engine. When attached, **every tool call goes through policy evaluation before reaching the backend**. The default mode is DENY — an empty engine blocks all tool calls. See the [Identity, Policy & IAM](../policy) section for the full model.

## Error Types

The SDK raises typed exceptions for common failure modes:

| Exception | When |
|-----------|------|
| `GatewayPolicyDeniedError` | Cedar policy returned DENY (HTTP 403) |
| `GatewayConfigError` | Missing URL, region, or JWT configuration |
| `GatewayError` | General gateway failure (base class) |

## Why Agents Never Know What's Behind Their Tools

This design is intentional. Decoupling agents from tool implementations means:

- Backend infrastructure can change (Lambda → REST → new service) without modifying agent code
- Credentials stay in one place (resolved by Gateway), not scattered across agent codebases
- Policy enforcement happens centrally at Gateway, not per-agent
- Tool discovery works across all backends uniformly

An agent that knows it is calling a Lambda function is fragile. An agent that calls MCP tools through Gateway is resilient.

## See Also

- [Gateway SDK Reference](../sdk/gateway) — `GatewayClient`, `TargetRegistry`, `ToolDiscovery`
- [Identity, Policy & IAM](../policy) — how user tokens flow through inbound/outbound auth
- [Cedar Policy](../policy/cedar-policy) — policy engine attached to Gateway
