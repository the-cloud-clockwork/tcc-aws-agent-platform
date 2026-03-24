---
title: MCP
parent: Concepts
nav_order: 10
---

# MCP (Model Context Protocol)

The platform provides base classes for building MCP servers that domain repos consume. Every MCP server in the ecosystem extends `BaseMCPServer` from `agent_core.mcp.base_server`, giving it transport handling, observability, and caching for free.

## BaseMCPServer

`BaseMCPServer` eliminates the boilerplate duplicated across MCP servers. It provides:

- **Transport selection** -- stdio, HTTP (streamable), or SSE via `MCP_TRANSPORT` env var
- **Tool registration** via a `@mcp.tool()` decorator that accepts an MCP `Tool` definition
- **Error wrapping** -- exceptions in tool handlers are caught and returned as structured JSON error responses
- **Health endpoint** -- HTTP/SSE transports automatically expose `/health`
- **Background tasks** -- optional coroutines that run alongside the server (e.g., polling loops)
- **Observability integration** -- automatic structured logging and OTEL spans for every tool call

### Usage

```python
from agent_core.mcp.base_server import BaseMCPServer
from mcp.types import Tool

mcp = BaseMCPServer("my-mcp-server", default_port=8004)

@mcp.tool(Tool(
    name="get_data",
    description="Fetch data by ID",
    inputSchema={"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
))
async def get_data(arguments: dict) -> dict:
    return {"result": "..."}

if __name__ == "__main__":
    mcp.run()
```

## Cache Layer

The `agent_core.mcp.cache` module provides a Redis-backed caching layer for MCP servers. Features:

- **Lazy initialization** -- Redis client connects on first use
- **Graceful degradation** -- if Redis is unavailable, caching is silently disabled
- **Deterministic keys** -- cache keys are built from a namespace + SHA256 hash of the arguments
- **Configurable TTL** -- default 300 seconds, overridable per call
- **Namespace prefixes** -- isolate cache entries across different MCP servers

```python
from agent_core.mcp.cache import cache_get, cache_set

# Check cache
result = cache_get("catalog", item_id="SKU-42", region="us-east-1")
if result is None:
    result = fetch_from_api(...)
    cache_set("catalog", result, ttl_seconds=600, item_id="SKU-42", region="us-east-1")
```

## Provider Routing

`agent_core.mcp.provider_routing` eliminates the duplicated `get_provider()` pattern across domain MCP servers. Each server declares a registry mapping execution modes to provider classes:

```python
from agent_core.mcp.provider_routing import resolve_provider
from agent_core.execution.mode import ExecutionMode

PROVIDERS = {
    ExecutionMode.SIMULATION: MockProvider,
    ExecutionMode.STAGING: LiveProvider,
    ExecutionMode.PRODUCTION: LiveProvider,
}
provider = resolve_provider(PROVIDERS)
```

This reads the `EXECUTION_MODE` environment variable, resolves the matching provider class, and instantiates it. If no provider is registered for the current mode, it raises `ValueError`.

## Observability

`MCPObservabilityHook` integrates with `BaseMCPServer` to emit:

- **Structured JSON logs** for every tool invocation (CloudWatch-queryable)
- **OpenTelemetry spans** when OTEL is configured

The hook is auto-enabled when `MCP_OBSERVABILITY=true` or `OTEL_ENABLED=true` is set. Each tool call records: request ID, server ID, tool name, execution mode, duration, and success/failure status.

## How Domain Repos Build MCP Servers

Domain repos import `BaseMCPServer` from `agent-core` and register domain-specific tools:

1. Create a Python module with `mcp = BaseMCPServer("domain-mcp", default_port=8004)`
2. Define tools with `@mcp.tool(Tool(...))` decorators
3. Use `cache_get`/`cache_set` for data that benefits from caching
4. Use `resolve_provider` to swap data sources by execution mode
5. Package as a Docker container with `mcp.run()` as the entrypoint
