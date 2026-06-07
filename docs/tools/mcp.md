---
title: MCP Servers
nav_order: 2
parent: "Tools, MCP & Gateway"
---

# MCP Servers

The platform provides a base class for building MCP (Model Context Protocol) servers that integrate with the Gateway, observability pipeline, and provider routing infrastructure. Every MCP server in the ecosystem extends `BaseMCPServer` from `agent_core.mcp.base_server`, giving it transport handling, tool registration, error wrapping, and observability without boilerplate.

## BaseMCPServer

`BaseMCPServer` wraps `mcp.server.Server` from the `mcp` library and handles:

- **Transport selection** — `stdio`, `http` (Streamable HTTP via Starlette/uvicorn), or `sse` (legacy SSE) via the `MCP_TRANSPORT` env var
- **Tool registration** via the `@mcp.tool()` decorator — accepts an MCP `Tool` definition with name, description, and input schema
- **JSON Schema `$defs` flattening** — AgentCore Gateway rejects tool schemas containing `$defs` references; `BaseMCPServer` automatically inlines all `$defs` at registration time so authors never need to work around this
- **Error wrapping** — exceptions in tool handlers are caught and returned as structured JSON `TextContent` responses with the exception type, message, and traceback
- **Health endpoints** — HTTP mode exposes `/ping` and `/health`; SSE mode exposes `/health`
- **Background tasks** — optional coroutines run alongside the server via `add_background_task()` (useful for polling loops)
- **Observability** — `MCPObservabilityHook` emits structured logs and OTEL spans per tool call when `MCP_OBSERVABILITY=true` or `OTEL_ENABLED=true` is set

### Transports and Endpoints

| Transport | `MCP_TRANSPORT` | MCP endpoint | Health |
|-----------|----------------|-------------|--------|
| Streamable HTTP | `http` | `/mcp`, `/` | `/ping`, `/health` |
| SSE (legacy) | `sse` | `/sse`, `/messages` | `/health` |
| stdio | `stdio` | stdin/stdout | — |

HTTP mode is the standard for Gateway-registered MCP Runtime targets. stdio is used for local tooling and testing.

### Usage

```python
from agent_core.mcp.base_server import BaseMCPServer
from mcp.types import Tool

mcp = BaseMCPServer("catalog-server", default_port=8004)

@mcp.tool(Tool(
    name="get_item",
    description="Fetch a catalog item by SKU",
    inputSchema={
        "type": "object",
        "properties": {
            "sku": {"type": "string", "description": "Product SKU"},
            "region": {"type": "string", "description": "Warehouse region"},
        },
        "required": ["sku"],
    },
))
async def get_item(arguments: dict) -> dict:
    sku = arguments["sku"]
    region = arguments.get("region", "default")
    return {"sku": sku, "region": region, "stock": 42}

if __name__ == "__main__":
    mcp.run()  # Reads MCP_TRANSPORT; defaults to stdio
```

### The $defs Flattening Gotcha

Pydantic models generate JSON schemas with `$defs` blocks for nested types. AgentCore Gateway rejects these schemas. `BaseMCPServer` automatically flattens `$defs` by inlining the referenced definitions at registration time — you do not need to hand-craft flat schemas when using `BaseMCPServer`. This happens transparently in the `@mcp.tool()` decorator.

### Background Tasks

Register coroutines to run alongside the server using `add_background_task()`. The task factory is called when the server starts and cancelled on shutdown:

```python
import asyncio

async def refresh_cache():
    while True:
        await load_cache_from_db()
        await asyncio.sleep(300)

mcp.add_background_task(refresh_cache)
```

Background tasks only run in `stdio` mode. In `http` and `sse` modes, use Starlette's lifespan mechanism for startup/shutdown hooks.

## Cache Layer

`agent_core.mcp.cache` provides a Redis-backed result cache for tool calls. It uses module-level functions (not a class) with lazy Redis initialisation and graceful degradation — if Redis is unavailable, caching is silently disabled and tool calls proceed normally.

```python
from agent_core.mcp.cache import cache_get, cache_set

@mcp.tool(Tool(name="get_item", description="...", inputSchema={...}))
async def get_item(arguments: dict) -> dict:
    sku = arguments["sku"]

    # Check cache first
    cached = cache_get("catalog", sku=sku)
    if cached is not None:
        return cached

    result = await fetch_from_db(sku)
    cache_set("catalog", result, ttl_seconds=600, sku=sku)
    return result
```

**Key characteristics:**
- Cache keys are built from a namespace string plus a SHA-256 hash of the keyword arguments (deterministic, safe for arbitrary arg types)
- Default TTL is 300 seconds, overridable per call via `ttl_seconds`
- Redis URL is read from `REDIS_URL` env var (default: `redis://localhost:6379/0`)
- No configuration class or YAML block — the module reads env vars directly

## Provider Routing

`agent_core.mcp.provider_routing` eliminates the repeated `get_provider()` pattern across MCP servers. Each server declares a dict mapping `ExecutionMode` enum values to provider classes:

```python
from agent_core.mcp.provider_routing import resolve_provider
from agent_core.execution.mode import ExecutionMode

PROVIDERS = {
    ExecutionMode.SIMULATION: MockCatalogProvider,
    ExecutionMode.STAGING: LiveCatalogProvider,
    ExecutionMode.PRODUCTION: LiveCatalogProvider,
}

# Reads EXECUTION_MODE env var, instantiates the correct provider
provider = resolve_provider(PROVIDERS)
```

`resolve_provider()` reads the `EXECUTION_MODE` environment variable, looks up the matching class in the registry, and instantiates it with no arguments. If no provider is registered for the current mode, it raises `ValueError` listing the available modes.

This is a function, not a class — there is no `MCPProviderRouter.from_config()` classmethod.

## Building a Domain MCP Server

Domain repos follow this pattern:

1. Import `BaseMCPServer` from the `agent-core` package
2. Instantiate it with a server name and default port
3. Register tools with `@mcp.tool(Tool(...))`
4. Use `cache_get`/`cache_set` for expensive lookups
5. Use `resolve_provider()` to swap data sources by execution mode
6. Package as a Docker container with `mcp.run()` as the entrypoint

```python
#!/usr/bin/env python3
"""Catalog MCP server — exposes catalog lookup tools via MCP."""

from agent_core.mcp.base_server import BaseMCPServer
from agent_core.mcp.cache import cache_get, cache_set
from agent_core.mcp.provider_routing import resolve_provider
from agent_core.execution.mode import ExecutionMode
from mcp.types import Tool

from catalog_server.providers import MockProvider, LiveProvider

PROVIDERS = {
    ExecutionMode.SIMULATION: MockProvider,
    ExecutionMode.STAGING: LiveProvider,
    ExecutionMode.PRODUCTION: LiveProvider,
}

mcp = BaseMCPServer("catalog-mcp", default_port=8004)
provider = resolve_provider(PROVIDERS)


@mcp.tool(Tool(
    name="search_catalog",
    description="Search products by keyword",
    inputSchema={
        "type": "object",
        "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["query"],
    },
))
async def search_catalog(arguments: dict) -> list:
    query = arguments["query"]
    limit = arguments.get("limit", 10)

    cached = cache_get("search", query=query, limit=limit)
    if cached is not None:
        return cached

    results = await provider.search(query, limit=limit)
    output = [{"id": r.id, "name": r.name, "score": r.score} for r in results]
    cache_set("search", output, ttl_seconds=300, query=query, limit=limit)
    return output


if __name__ == "__main__":
    mcp.run()
```

## How Agents Consume MCP Servers

MCP servers are registered as Gateway targets (type `mcp_server`) via the domain repo's `gateway-targets.yaml`. Agents do not connect to MCP servers directly — they go through the Gateway:

```
Agent ──MCP──> Gateway ──OAuth2 Bearer──> Catalog MCP Runtime
                                          (BaseMCPServer on :8004)
```

From the agent's perspective, `catalog-mcp` tools appear alongside Lambda tools and built-in tools as a unified flat tool list from `client.list_tools_sync()`.

## Naming Convention

MCP servers in the ecosystem follow the `-mcp` suffix convention: `catalog-mcp`, `analytics-mcp`, `data-ingest-mcp`. This convention is not enforced by the platform but makes Gateway target names and ECR repository names consistent across domain repos.

## See Also

- [Gateway](gateway) — how MCP servers are registered as Gateway targets and consumed by agents
- [Gateway SDK Reference](../sdk/gateway) — `GatewayClient`, `TargetRegistry`
- [MCP SDK Reference](../sdk/mcp) — full API reference for `BaseMCPServer`, `cache_get`/`cache_set`, `resolve_provider`
