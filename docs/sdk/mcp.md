---
title: MCP Base Classes
nav_order: 10
parent: SDK Reference
---

# MCP Base Classes

The MCP subsystem provides base classes for building domain-specific MCP (Model Context Protocol) servers that integrate cleanly with the platform's gateway, caching, and routing infrastructure. Domain repos extend these classes rather than building MCP servers from scratch.

## Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `BaseMCPServer` | `agent_core.mcp.base_server` | Shared server skeleton — tool registration, transport selection, error wrapping, health endpoint |
| `MCPCache` | `agent_core.mcp.cache` | Shared cache layer for MCP tool results |
| `MCPProviderRouter` | `agent_core.mcp.provider_routing` | Routes tool calls to the correct backend provider |
| `MCPVersionedStore` | `agent_core.mcp.versioned_store` | Versioned key-value store for MCP server state |

## BaseMCPServer

`BaseMCPServer` handles the boilerplate of running an MCP server: transport selection (stdio, HTTP, SSE), tool registration via decorators, error wrapping on `call_tool` responses, health endpoint, background task hooks, and logging setup. It wraps the upstream `mcp.server.Server` from the `mcp` library (which itself builds on `FastMCP` from `mcp.server.fastmcp`).

Domain servers instantiate `BaseMCPServer` and register tools using the `@mcp.tool()` decorator:

```python
from agent_core.mcp.base_server import BaseMCPServer
from mcp.types import Tool

mcp = BaseMCPServer("document-server", default_port=8080)

@mcp.tool(Tool(name="get_document", description="Retrieve a document by ID", inputSchema={
    "type": "object",
    "properties": {"document_id": {"type": "string"}},
    "required": ["document_id"],
}))
async def get_document(arguments: dict) -> dict:
    doc_id = arguments["document_id"]
    doc = await store.get(doc_id)
    return {"id": doc.id, "content": doc.content}

@mcp.tool(Tool(name="search_documents", description="Search documents", inputSchema={
    "type": "object",
    "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}},
    "required": ["query"],
}))
async def search_documents(arguments: dict) -> list:
    results = await search_index.query(arguments["query"], arguments.get("top_k", 10))
    return [{"id": r.id, "score": r.score} for r in results]

if __name__ == "__main__":
    mcp.run()
```

`BaseMCPServer` automatically:
- Selects transport based on `MCP_TRANSPORT` env var (`stdio`, `http`, or `sse`)
- Exposes HTTP health endpoint at `/health` and MCP endpoint at `/mcp` (HTTP mode) or `/sse` + `/messages` (SSE mode)
- Wraps tool handler errors into JSON `TextContent` responses with traceback
- Integrates `MCPObservabilityHook` for tool call metrics
- Supports background tasks via `add_background_task()` for polling patterns

## MCPCache

`MCPCache` is a shared result cache that prevents redundant calls to expensive backends (databases, external APIs). It uses a pluggable backend — ElastiCache (Redis) in production or an in-process dict for local development:

```python
from agent_core.mcp.cache import MCPCache

cache = MCPCache.from_config(config)

cached = await cache.get("doc:123")
if not cached:
    result = await fetch_document("123")
    await cache.set("doc:123", result, ttl_seconds=300)
```

Cache configuration in the server config YAML:

```yaml
cache:
  backend: redis               # redis | memory
  redis_url: "${REDIS_URL}"
  default_ttl_seconds: 300
  max_size_mb: 128
```

## MCPProviderRouter

`MCPProviderRouter` routes tool calls to different backend providers based on the request context. Use this when a single tool needs to fan out to multiple data sources or switch providers by environment:

```python
from agent_core.mcp.provider_routing import MCPProviderRouter

router = MCPProviderRouter.from_config(config)

provider = router.resolve("primary")
result = await provider.query(query)
```

Router configuration:

```yaml
providers:
  primary:
    type: opensearch
    endpoint: "${OPENSEARCH_ENDPOINT}"
  archive:
    type: s3
    bucket: "${ARCHIVE_BUCKET}"
  default: primary
```

## MCPVersionedStore

`MCPVersionedStore` is a lightweight versioned key-value store backed by DynamoDB. Use it to persist MCP server state that needs audit history or rollback capability:

```python
from agent_core.mcp.versioned_store import MCPVersionedStore

vstore = MCPVersionedStore.from_config(config)

# Get current or specific version
current = await vstore.get("config-key")
old = await vstore.get("config-key", version="3")

# Put new version
version = await vstore.put("config-key", {"setting": "value"})

# List version history
versions = await vstore.list_versions("config-key")
```

## Gateway Auto-Registration

When `gateway.auto_register: true` is set, `BaseMCPServer` registers itself as a Gateway target at startup and deregisters at shutdown. This means the server's tools appear automatically in `ToolDiscovery` without any manual Gateway configuration:

```yaml
# server-config.yaml
gateway:
  auto_register: true
  gateway_endpoint: "${GATEWAY_ENDPOINT}"
  target_name: "document-server"
  auth:
    type: api_key
    secret_arn: "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:mcp-server-key"
```

## Building a Domain MCP Server

The recommended pattern for domain repos:

1. Create a new Python package (e.g., `my-domain-mcp`)
2. Instantiate `BaseMCPServer` and register tools with `@mcp.tool()`
3. Use `MCPCache` for expensive lookups
4. Use `MCPProviderRouter` if you have multiple data sources
5. Package as a Docker container and deploy via the platform's `agents/` Terraform module

The platform's Terraform infrastructure provisions the ECR repository, ECS service, and Gateway target registration. Domain repos only write Python.
