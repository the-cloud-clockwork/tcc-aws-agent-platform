"""Base MCP server — eliminates boilerplate duplicated across all MCP servers.

Provides logging setup, transport selection (stdio/http/sse), health endpoint,
error wrapping for call_tool responses, and optional background task hooks.

Usage:
    from agent_core.mcp.base_server import BaseMCPServer
    from mcp.types import Tool

    mcp = BaseMCPServer("my-mcp", default_port=8080)

    @mcp.tool(Tool(name="get_data", description="...", inputSchema={...}))
    async def get_data(arguments: dict) -> dict:
        return {"items": [...]}}

    if __name__ == "__main__":
        mcp.run()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import traceback
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from agent_core.mcp.observability import MCPObservabilityHook, auto_hook

logger = logging.getLogger(__name__)


class BaseMCPServer:
    """Shared MCP server skeleton for all domain and platform MCP servers.

    Handles:
    - Logging setup (LOG_LEVEL env var)
    - Tool registration via decorator
    - Tool dispatch with error wrapping
    - Transport selection (stdio/http/sse via MCP_TRANSPORT env var)
    - HTTP health endpoint
    - Optional background tasks (e.g. background polling)
    """


    @staticmethod
    def _flatten_defs(schema: dict) -> dict:
        """Inline $defs references -- AgentCore Gateway rejects JSON Schema $defs."""
        import copy as _copy
        defs = schema.pop("$defs", {})
        if not defs:
            return schema
        def _resolve(obj):
            if isinstance(obj, dict):
                if "$ref" in obj:
                    ref_name = obj["$ref"].split("/")[-1]
                    if ref_name in defs:
                        return _resolve(_copy.deepcopy(defs[ref_name]))
                return {k: _resolve(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_resolve(i) for i in obj]
            return obj
        return _resolve(schema)

    def __init__(
        self,
        name: str,
        *,
        default_port: int = 8000,
        observability: MCPObservabilityHook | None = None,
    ) -> None:
        self.name = name
        self.default_port = default_port
        self.server = Server(name)
        self._tools: list[Tool] = []
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}
        self._background_tasks: list[Callable[[], Coroutine[Any, Any, None]]] = []
        self._observability = observability if observability is not None else auto_hook(name)

        # Configure logging
        level = os.environ.get("LOG_LEVEL", "INFO").upper()
        logging.basicConfig(
            level=getattr(logging, level, logging.INFO),
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        )

        # Wire up MCP protocol handlers
        self.server.list_tools()(self._list_tools)
        self.server.call_tool()(self._call_tool)

    def tool(self, definition: Tool) -> Callable:
        """Decorator to register a tool handler.

        The decorated function receives ``arguments: dict`` and must return
        a JSON-serialisable value. Errors are automatically wrapped.

        Example::

            @mcp.tool(Tool(name="get_data", description="...", inputSchema={...}))
            async def get_data(arguments: dict) -> dict:
                ...
        """

        def decorator(fn: Callable[..., Coroutine[Any, Any, Any]]) -> Callable:
            # Flatten $defs -- AgentCore Gateway does not support JSON Schema $defs
            if definition.inputSchema:
                schema_str = json.dumps(definition.inputSchema)
                if "$defs" in schema_str:
                    definition = Tool(
                        name=definition.name,
                        description=definition.description,
                        inputSchema=self._flatten_defs(dict(definition.inputSchema)),
                    )
            self._tools.append(definition)
            self._handlers[definition.name] = fn
            return fn

        return decorator

    def add_background_task(self, coro_factory: Callable[[], Coroutine[Any, Any, None]]) -> None:
        """Register a coroutine to run as a background task in stdio mode.

        The factory is called (with no args) to create the coroutine when
        the server starts. The task is cancelled on server shutdown.
        """
        self._background_tasks.append(coro_factory)

    # -- Protocol handlers ---------------------------------------------------

    async def _list_tools(self) -> list[Tool]:
        return self._tools

    async def _call_tool(self, name: str, arguments: dict) -> list[TextContent]:
        handler = self._handlers.get(name)
        if handler is None:
            error = {"error": "ValueError", "message": f"Unknown tool: {name}"}
            return [TextContent(type="text", text=json.dumps(error))]

        record = self._observability.on_tool_start(name) if self._observability else None
        try:
            result = await handler(arguments)
            if record is not None:
                self._observability.on_tool_end(record)
            return [TextContent(type="text", text=json.dumps(result, default=str))]
        except Exception as e:
            logger.error("Tool %s failed: %s", name, e)
            if record is not None:
                self._observability.on_tool_end(record, error=e)
            error_detail = {
                "error": type(e).__name__,
                "message": str(e),
                "traceback": traceback.format_exc(),
            }
            return [TextContent(type="text", text=json.dumps(error_detail))]

    # -- Transport runners ---------------------------------------------------

    async def _run_stdio(self) -> None:
        """Run MCP server over stdio transport."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream, write_stream, self.server.create_initialization_options()
            )

    async def _run_stdio_with_background(self) -> None:
        """Run stdio transport with background tasks."""
        tasks: list[asyncio.Task] = []
        try:
            for factory in self._background_tasks:
                tasks.append(asyncio.create_task(factory()))
            await self._run_stdio()
        finally:
            for t in tasks:
                t.cancel()

    def _run_http(self) -> None:
        """Run MCP server over streamable HTTP transport."""
        import contextlib

        import uvicorn
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Mount, Route

        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", str(self.default_port)))
        session_manager = StreamableHTTPSessionManager(app=self.server, stateless=True)

        async def ping(_request: Any) -> JSONResponse:
            return JSONResponse({"status": "healthy"})

        @contextlib.asynccontextmanager
        async def lifespan(_app: Any) -> AsyncIterator[None]:
            async with session_manager.run():
                yield

        starlette_app = Starlette(
            routes=[
                Route("/ping", endpoint=ping),
                Route("/health", endpoint=ping),
                Mount("/mcp", app=session_manager.handle_request),
                Mount("/", app=session_manager.handle_request),
            ],
            lifespan=lifespan,
        )
        logger.info("Starting HTTP transport on %s:%d", host, port)
        config = uvicorn.Config(starlette_app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        asyncio.run(server.serve())

    def _run_sse(self) -> None:
        """Run MCP server over SSE transport (legacy SSE transport)."""
        import uvicorn
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        sse = SseServerTransport("/messages")
        app = self.server

        async def handle_sse(request: Any) -> None:
            async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                await app.run(streams[0], streams[1], app.create_initialization_options())

        async def health(_request: Any) -> JSONResponse:
            return JSONResponse({"status": "ok"})

        starlette_app = Starlette(routes=[
            Route("/health", endpoint=health),
            Route("/sse", endpoint=handle_sse),
            Route("/messages", endpoint=sse.handle_post_message, methods=["POST"]),
        ])
        port = int(os.environ.get("MCP_PORT", str(self.default_port)))
        uvicorn.run(starlette_app, host="0.0.0.0", port=port)

    def run(self) -> None:
        """Start the server. Reads MCP_TRANSPORT env var (stdio|http|sse)."""
        transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()

        if transport == "stdio":
            if self._background_tasks:
                asyncio.run(self._run_stdio_with_background())
            else:
                asyncio.run(self._run_stdio())
        elif transport == "http":
            self._run_http()
        elif transport == "sse":
            self._run_sse()
        else:
            logger.error(
                "Unknown MCP_TRANSPORT=%s. Use 'stdio', 'http', or 'sse'.", transport
            )
            sys.exit(1)
