"""MCP server entrypoint for Artifacts."""

from __future__ import annotations

import json
import logging
import os
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from mcp_artifacts.catalog import ArtifactCatalog
from mcp_artifacts.storage import ArtifactStorage
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
            "data export, pipeline run) to S3 and register it in the artifact catalog. "
            "Returns the artifact_id and S3 key immediately."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["chart", "report", "simulation_result", "recommendation", "image", "data_export", "pipeline_run"],
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
                "tier": {
                    "type": "string",
                    "enum": ["platform", "domain"],
                    "description": "Artifact tier (default: platform)",
                    "default": "platform",
                },
                "kms_key_alias": {
                    "type": "string",
                    "description": "KMS key alias for server-side encryption",
                },
                "pipeline_date": {
                    "type": "string",
                    "description": "Analysis date (YYYY-MM-DD)",
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
                    "enum": ["chart", "report", "simulation_result", "recommendation", "image", "data_export", "pipeline_run"],
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
                "execution_id": {
                    "type": "string",
                    "description": "Filter by execution/run ID",
                },
            },
        },
    ),
    Tool(
        name="get_pipeline_run",
        description=(
            "Retrieve a pipeline run manifest by execution_id or date. "
            "Returns the manifest JSON content inline."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "execution_id": {
                    "type": "string",
                    "description": "Step Functions execution ID",
                },
                "date": {
                    "type": "string",
                    "description": "Analysis date (YYYY-MM-DD)",
                },
            },
        },
    ),
    Tool(
        name="get_latest_run",
        description=(
            "Get the most recent pipeline run manifest. "
            "Returns the manifest JSON content inline."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="get_agent_result",
        description=(
            "Retrieve a specific agent's result artifact from a pipeline run. "
            "Returns the artifact JSON content inline with a signed URL."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "execution_id": {
                    "type": "string",
                    "description": "Step Functions execution ID",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent identifier",
                },
            },
            "required": ["execution_id", "agent_id"],
        },
    ),
    Tool(
        name="search_artifacts",
        description=(
            "Search artifacts with date range, agent, type, and tier filters. "
            "Returns metadata and signed URLs (no S3 content)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "date_from": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD)",
                },
                "date_to": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD)",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Filter by agent ID",
                },
                "type": {
                    "type": "string",
                    "description": "Filter by artifact type",
                },
                "tier": {
                    "type": "string",
                    "enum": ["platform", "domain"],
                    "description": "Filter by tier",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20)",
                    "default": 20,
                },
            },
        },
    ),
]


@app.list_tools()
async def handle_list_tools() -> list[Tool]:
    """Return all available artifact tools."""
    return TOOLS




async def _get_pipeline_run(
    execution_id: str = "",
    date: str = "",
) -> dict:
    """Retrieve a pipeline run manifest by execution_id or date."""
    catalog = ArtifactCatalog()
    storage = ArtifactStorage()

    if not execution_id and not date:
        return {"error": "At least one of execution_id or date is required"}

    if execution_id:
        entries = catalog.list_entries(
            artifact_type="pipeline_run",
            execution_id=execution_id,
            limit=1,
        )
    else:
        entries = catalog.list_entries(
            artifact_type="pipeline_run",
            date=date,
            limit=1,
        )

    if not entries:
        return {"error": "Pipeline run not found"}

    entry = entries[0]
    try:
        content = storage.get_object_bytes(entry["s3_key"]).decode("utf-8")
        import json as _json
        manifest = _json.loads(content)
    except Exception as e:
        manifest = {"error": f"Failed to fetch manifest: {e}"}

    return {
        "artifact_id": entry["artifact_id"],
        "execution_id": entry.get("execution_id", ""),
        "pipeline_date": entry.get("pipeline_date", ""),
        "created_at": entry.get("created_at", ""),
        "manifest": manifest,
    }


async def _get_latest_run() -> dict:
    """Get the most recent pipeline run manifest."""
    catalog = ArtifactCatalog()
    storage = ArtifactStorage()

    entries = catalog.list_entries(
        artifact_type="pipeline_run",
        limit=1,
    )

    if not entries:
        return {"error": "No pipeline runs found"}

    entry = entries[0]
    try:
        content = storage.get_object_bytes(entry["s3_key"]).decode("utf-8")
        import json as _json
        manifest = _json.loads(content)
    except Exception as e:
        manifest = {"error": f"Failed to fetch manifest: {e}"}

    return {
        "artifact_id": entry["artifact_id"],
        "execution_id": entry.get("execution_id", ""),
        "pipeline_date": entry.get("pipeline_date", ""),
        "created_at": entry.get("created_at", ""),
        "manifest": manifest,
    }


async def _get_agent_result(
    execution_id: str,
    agent_id: str,
) -> dict:
    """Retrieve a specific agent's result artifact from a pipeline run."""
    catalog = ArtifactCatalog()
    storage = ArtifactStorage()

    entries = catalog.list_entries(
        execution_id=execution_id,
        agent_id=agent_id,
        limit=1,
    )

    if not entries:
        return {"error": f"No artifact found for agent {agent_id} in execution {execution_id}"}

    entry = entries[0]
    signed_url = storage.get_best_url(entry["s3_key"])

    result: dict = {
        "artifact_id": entry["artifact_id"],
        "agent_id": entry.get("agent_id", ""),
        "execution_id": entry.get("execution_id", ""),
        "type": entry.get("type", ""),
        "status": entry.get("status", ""),
        "created_at": entry.get("created_at", ""),
        "signed_url": signed_url,
        "metadata": entry.get("metadata", {}),
    }

    # Inline JSON content for JSON-type artifacts
    if entry.get("status") == "ready" and entry.get("type") in ("simulation_result", "recommendation", "pipeline_run", "data_export", "report"):
        try:
            raw = storage.get_object_bytes(entry["s3_key"]).decode("utf-8")
            import json as _json
            result["content"] = _json.loads(raw)
        except Exception:
            pass  # content not included, signed_url available

    return result


async def _search_artifacts(
    date_from: str = "",
    date_to: str = "",
    agent_id: str = "",
    type: str = "",
    tier: str = "",
    limit: int = 20,
) -> dict:
    """Search artifacts with filters. Returns metadata + signed URLs."""
    catalog = ArtifactCatalog()
    storage = ArtifactStorage()

    # Use the most specific query path available
    entries = catalog.list_entries(
        artifact_type=type or None,
        agent_id=agent_id or None,
        date=date_from or None,
        limit=limit,
    )

    # Apply additional filters that list_entries doesn't natively support
    filtered = []
    for entry in entries:
        if tier and entry.get("tier", "platform") != tier:
            continue
        if date_to and entry.get("created_at", "") > date_to + "T99":
            continue
        filtered.append(entry)

    results = []
    for entry in filtered[:limit]:
        signed_url = storage.get_best_url(entry["s3_key"]) if entry.get("status") == "ready" else None
        results.append({
            "artifact_id": entry["artifact_id"],
            "type": entry.get("type", ""),
            "agent_id": entry.get("agent_id", ""),
            "execution_id": entry.get("execution_id", ""),
            "tier": entry.get("tier", "platform"),
            "pipeline_date": entry.get("pipeline_date", ""),
            "status": entry.get("status", ""),
            "created_at": entry.get("created_at", ""),
            "signed_url": signed_url,
            "metadata": entry.get("metadata", {}),
        })

    return {"count": len(results), "artifacts": results}


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Dispatch tool calls to the appropriate handler."""
    handlers = {
        "create_artifact": create_artifact,
        "get_artifact": get_artifact,
        "poll_artifact": poll_artifact,
        "list_artifacts": list_artifacts,
        "get_pipeline_run": _get_pipeline_run,
        "get_latest_run": _get_latest_run,
        "get_agent_result": _get_agent_result,
        "search_artifacts": _search_artifacts,
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
