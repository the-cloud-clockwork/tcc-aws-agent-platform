---
title: MCP Base Classes
nav_order: 10
parent: SDK Reference
---

# MCP Base Classes

The MCP subsystem provides base classes for building domain-specific MCP (Model Context Protocol) servers that integrate cleanly with the platform's Gateway, caching, and provider routing. Domain repos extend `BaseMCPServer` rather than building MCP servers from scratch.

> **Architecture guide:** [Tools, MCP & Gateway](../tools.md)

## Key Classes and Functions

| Class / Function | Module | Purpose |
|-----------------|--------|---------|
| `BaseMCPServer` | `agent_core.mcp.base_server` | Shared server skeleton — tool registration, transport selection, health endpoint, `$defs` flattening |
| `cache_get()` / `cache_set()` | `agent_core.mcp.cache` | Module-level cache functions backed by Redis or in-process dict |
| `resolve_provider()` | `agent_core.mcp.provider_routing` | Resolves the correct provider class from `EXECUTION_MODE` env var |

## `BaseMCPServer`

`BaseMCPServer` wraps `mcp.server.Server` directly (no FastMCP dependency). It handles transport selection, tool registration, error wrapping, health endpoints, and background tasks.

> **Critical:** `BaseMCPServer` flattens JSON Schema `$defs` on tool registration. AgentCore Gateway rejects tool schemas that contain `$defs` references — the flattening is applied automatically to every registered tool schema so domain authors do not need to handle it manually.

```python
from agent_core.mcp.base_server import BaseMCPServer
from mcp.types import Tool

mcp = BaseMCPServer("document-server", default_port=8080)

@mcp.tool(Tool(
    name="get_document",
    description="Retrieve a document by ID",
    inputSchema={
        "type": "object",
        "properties": {"document_id": {"type": "string"}},
        "required": ["document_id"],
    },
))
async def get_document(arguments: dict) -> dict:
    doc_id = arguments["document_id"]
    doc = await store.get(doc_id)
    return {"id": doc.id, "content": doc.content}

if __name__ == "__main__":
    mcp.run()
```

### `BaseMCPServer` API

```python
class BaseMCPServer:
    def __init__(
        self,
        name: str,
        default_port: int = 8080,
    ) -> None: ...

    def tool(self, definition: Tool) -> Callable:
        """Decorator. Registers an async function as an MCP tool.
        Automatically flattens $defs in the inputSchema before registration."""
        ...

    def add_background_task(self, coro_factory: Callable[[], Coroutine]) -> None:
        """Register a background coroutine factory. Runs alongside the server."""
        ...

    def run(self) -> None:
        """Start the server. Transport selected via MCP_TRANSPORT env var."""
        ...
```

### Transport Selection (`MCP_TRANSPORT` env var)

| `MCP_TRANSPORT` value | Transport | Endpoints |
|----------------------|-----------|-----------|
| `stdio` (default) | Stdio JSON-RPC | — |
| `http` | Streamable HTTP (Starlette/uvicorn) | `GET /ping`, `GET /health`, `POST /mcp`, `POST /` |
| `sse` | Legacy SSE | `GET /health`, `GET /sse`, `POST /messages` |

## `cache_get()` / `cache_set()`

Module-level cache functions backed by Redis (when `REDIS_URL` is set) or an in-process dict:

```python
from agent_core.mcp.cache import cache_get, cache_set

# Namespace + kwargs form a cache key
cached = cache_get("documents", prefix="v2", doc_id="abc-123")
if cached is None:
    result = await fetch_document("abc-123")
    cache_set("documents", result, 300, prefix="v2", doc_id="abc-123")
```

```python
def cache_get(
    namespace: str,
    *,
    prefix: str = "",
    **kwargs,             # Remaining kwargs form the deterministic SHA-256 cache key
) -> Any | None: ...

def cache_set(
    namespace: str,
    value: Any,
    ttl_seconds: int = 300,   # Positional arg — default 300 s
    *,
    prefix: str = "",
    **kwargs,
) -> None: ...
```

No class instantiation or configuration YAML is needed. Redis connection is read from `REDIS_URL` at first use. If Redis is unavailable at first use, caching is silently disabled for the process lifetime — tool calls proceed normally.

## `resolve_provider()`

Routes to the correct provider class based on `EXECUTION_MODE` env var. Each MCP server declares a registry dict mapping `ExecutionMode` to a provider class, then calls `resolve_provider()`:

```python
from agent_core.mcp.provider_routing import resolve_provider
from agent_core.execution.mode import ExecutionMode

PROVIDERS = {
    ExecutionMode.SIMULATION: MockDataProvider,
    ExecutionMode.STAGING: StagingAPIProvider,
    ExecutionMode.PRODUCTION: ProductionAPIProvider,
}

# Reads EXECUTION_MODE, picks the class, instantiates it
provider = resolve_provider(PROVIDERS)
```

```python
def resolve_provider(
    registry: dict[ExecutionMode, type[T]],
    *,
    aliases: dict[str, str] | None = None,  # Optional mode name aliases
) -> T: ...
```

The selected provider class is always instantiated with no arguments. Provider configuration should be read inside `__init__` from environment variables.

There is no `MCPProviderRouter` class. Provider routing is a single function call.

## Gateway Target Registration

Gateway target registration for an MCP server is performed by `TargetRegistry` at deploy time, not by `BaseMCPServer` at startup. There is no `gateway.auto_register` feature. See [Gateway SDK reference](gateway.md) for target registration details.

## Building a Domain MCP Server

Recommended pattern for domain repos:

1. Create a Python package (e.g., `analytics-mcp`)
2. Instantiate `BaseMCPServer` and register tools with `@mcp.tool()`
3. Use `cache_get` / `cache_set` for expensive lookups
4. Use `resolve_provider()` if different backends are needed per environment
5. Package as a Docker container; declare as a `mcp_server` target in `gateway-targets.yaml`

The platform's Terraform infrastructure provisions the ECR repository, ECS service, and Gateway target entry. Domain repos only write Python.

## See Also

- [Gateway SDK reference](gateway.md) — Target types, registration
- [Tools, MCP & Gateway guide](../tools.md) — Architecture, deployment patterns
