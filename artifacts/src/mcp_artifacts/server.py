"""MCP server entrypoint for Artifacts."""

from __future__ import annotations

import json
import logging
import os
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from mcp_artifacts.tools.create import create_artifact
from mcp_artifacts.tools.get import get_artifact
from mcp_artifacts.tools.list_artifacts import list_artifacts
from mcp_artifacts.tools.poll import poll_artifact

logger = logging.getLogger(__name__)

app = Server("mcp-artifacts")


# ------------------------------------------------------------------
# Tool definitions
# ------------------------------------------------------------------

TOOLS = [
    Tool(
        name="create_artifact",
        description=(
            "Store an artifact (chart, report, simulation result, recommendation, image, "
            "data export) to S3 and register it in the artifact catalog. Returns the "
            "artifact_id and S3 key immediately."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["chart", "report", "simulation_result", "recommendation", "image", "data_export"],
                    "description": "Artifact type",
                },
                "content": {
                    "type": "string",
                    "description": "Raw content. Base64 for image type, plain text for others.",
                },
                "metadata": {
                    "type": "object",
                    "description": "Arbitrary key/value metadata",
                    "default": {},
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent that produced this artifact",
                },
                "execution_id": {
                    "type": "string",
                    "description": "Execution or run identifier",
                },
            },
            "required": ["type", "content"],
        },
    ),
    Tool(
        name="get_artifact",
        description=(
            "Retrieve artifact metadata and a signed URL (if ready). "
            "Returns current status if the artifact is still processing."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "artifact_id": {
                    "type": "string",
                    "description": "UUID of the artifact",
                },
            },
            "required": ["artifact_id"],
        },
    ),
    Tool(
        name="poll_artifact",
        description=(
            "Poll until the artifact is ready (or timeout). Returns signed URL when ready."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "artifact_id": {
                    "type": "string",
                    "description": "UUID of the artifact",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "Max seconds to wait (default 60)",
                    "default": 60,
                },
            },
            "required": ["artifact_id"],
        },
    ),
    Tool(
        name="list_artifacts",
        description=(
            "List artifacts with optional filters. Returns metadata only (no URLs)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["chart", "report", "simulation_result", "recommendation", "image", "data_export"],
                    "description": "Filter by artifact type",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Filter by agent ID",
                },
                "date": {
                    "type": "string",
                    "description": "Filter by date (YYYY-MM-DD)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 50)",
                    "default": 50,
                },
            },
        },
    ),
]


@app.list_tools()
async def handle_list_tools() -> list[Tool]:
    """Return all available artifact tools."""
    return TOOLS


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch tool calls to the appropriate handler."""
    handlers = {
        "create_artifact": create_artifact,
        "get_artifact": get_artifact,
        "poll_artifact": poll_artifact,
        "list_artifacts": list_artifacts,
    }

    handler = handlers.get(name)
    if handler is None:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    try:
        result = await handler(**arguments)
        return [TextContent(type="text", text=json.dumps(result, default=str))]
    except Exception as e:
        logger.exception("Tool %s failed", name)
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


# ------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------

def main() -> None:
    """Run the MCP server — select transport based on MCP_TRANSPORT env var."""
    import asyncio

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()

    if transport == "stdio":
        async def _run() -> None:
            async with stdio_server() as (read_stream, write_stream):
                await app.run(read_stream, write_stream, app.create_initialization_options())

        asyncio.run(_run())
    elif transport == "http":
        import contextlib
        import uvicorn
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Mount, Route
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "8080"))
        session_manager = StreamableHTTPSessionManager(app=app, stateless=True)

        async def health(_request):
            return JSONResponse({"status": "ok"})

        @contextlib.asynccontextmanager
        async def lifespan(_app):
            async with session_manager.run():
                yield

        starlette_app = Starlette(
            routes=[
                Route("/health", endpoint=health),
                Mount("/mcp", app=session_manager.handle_request),
            ],
            lifespan=lifespan,
        )
        logging.info("Starting HTTP transport on %s:%d", host, port)
        config = uvicorn.Config(starlette_app, host=host, port=port, log_level="info")
        uvicorn_server = uvicorn.Server(config)
        asyncio.run(uvicorn_server.serve())
    else:
        logging.error("Unknown MCP_TRANSPORT=%s. Use 'stdio' or 'http'.", transport)
        sys.exit(1)


if __name__ == "__main__":
    main()
