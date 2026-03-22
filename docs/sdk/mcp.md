---
title: MCP Base Classes
nav_order: 10
---

# MCP Base Classes

The MCP subsystem provides base classes for building domain-specific MCP (Model Context Protocol) servers that integrate cleanly with the platform's gateway, caching, and routing infrastructure. Domain repos extend these classes rather than building MCP servers from scratch.

## Key Classes

| Class | Module | Purpose |
|-------|--------|---------|
| `BaseMCPServer` | `agent_core.mcp.base_server` | Base class for all platform MCP servers — registration, lifecycle, health |
| `MCPCache` | `agent_core.mcp.cache` | Shared cache layer for MCP tool results |
| `MCPProviderRouter` | `agent_core.mcp.provider_routing` | Routes tool calls to the correct backend provider |
| `MCPVersionedStore` | `agent_core.mcp.versioned_store` | Versioned key-value store for MCP server state |

## BaseMCPServer

`BaseMCPServer` handles the boilerplate of running an MCP server: starting the SSE or HTTP transport, registering tools, health checks, and graceful shutdown. Domain servers subclass it and declare their tools:

```python
from agent_core.mcp.base_server import BaseMCPServer
from mcp.server import tool

class DocumentServer(BaseMCPServer):
    """MCP server for document retrieval and indexing."""

    server_name = "document-server"
    server_version = "1.0"

    @tool()
    async def get_document(self, document_id: str) -> dict:
        """Retrieve a document by ID."""
        # Domain-specific implementation
        doc = await self.store.get(document_id)
        return {"id": doc.id, "content": doc.content, "metadata": doc.metadata}

    @tool()
    async def search_documents(self, query: str, top_k: int = 10) -> list:
        """Search documents by semantic similarity."""
        results = await self.search_index.query(query, top_k=top_k)
        return [{"id": r.id, "score": r.score, "snippet": r.snippet} for r in results]


# Entry point
if __name__ == "__main__":
    server = DocumentServer.from_config("server-config.yaml")
    server.run()
```

`BaseMCPServer` automatically:
- Exposes the MCP SSE endpoint at `/sse` and HTTP at `/mcp`
- Registers the server as a Gateway target (if `gateway.auto_register: true`)
- Publishes a health endpoint at `/health`
- Propagates X-Ray trace context from inbound requests

## MCPCache

`MCPCache` is a shared result cache that prevents redundant calls to expensive backends (databases, external APIs). It uses a pluggable backend — ElastiCache (Redis) in production or an in-process dict for local development:

```python
from agent_core.mcp.cache import MCPCache

class DocumentServer(BaseMCPServer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache = MCPCache.from_config(self.config)

    @tool()
    async def get_document(self, document_id: str) -> dict:
        cache_key = f"doc:{document_id}"

        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        doc = await self.store.get(document_id)
        result = {"id": doc.id, "content": doc.content}

        await self.cache.set(cache_key, result, ttl_seconds=300)
        return result
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

class DataServer(BaseMCPServer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.router = MCPProviderRouter.from_config(self.config)

    @tool()
    async def query_data(self, query: str, source: str = "primary") -> list:
        """Query data from the configured source."""
        provider = self.router.resolve(source)
        return await provider.query(query)
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

class ConfigServer(BaseMCPServer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.vstore = MCPVersionedStore.from_config(self.config)

    @tool()
    async def get_config(self, key: str, version: str = "latest") -> dict:
        return await self.vstore.get(key, version=version)

    @tool()
    async def set_config(self, key: str, value: dict) -> dict:
        version = await self.vstore.put(key, value)
        return {"key": key, "version": version}

    @tool()
    async def list_config_versions(self, key: str) -> list:
        return await self.vstore.list_versions(key)
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
2. Subclass `BaseMCPServer`
3. Declare tools with `@tool()` decorators
4. Use `MCPCache` for expensive lookups
5. Use `MCPProviderRouter` if you have multiple data sources
6. Package as a Docker container and deploy via the platform's `agents/` Terraform module

The platform's Terraform infrastructure provisions the ECR repository, ECS service, and Gateway target registration. Domain repos only write Python.
