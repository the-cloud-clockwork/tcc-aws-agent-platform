"""MCP server entrypoint for Artifacts — 8 tools via BaseMCPServer."""

from __future__ import annotations

import json
import logging

from mcp.types import Tool

from agent_core.mcp.base_server import BaseMCPServer

from mcp_artifacts.catalog import ArtifactCatalog
from mcp_artifacts.storage import ArtifactStorage
from mcp_artifacts.tools.create import create_artifact
from mcp_artifacts.tools.get import get_artifact
from mcp_artifacts.tools.list_artifacts import list_artifacts
from mcp_artifacts.tools.poll import poll_artifact

logger = logging.getLogger(__name__)

mcp = BaseMCPServer("mcp-artifacts", default_port=8004)


@mcp.tool(Tool(
    name="create_artifact",
    description="Store an artifact to S3 and register it in the artifact catalog. Returns artifact_id and S3 key.",
    inputSchema={
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["chart", "report", "simulation_result", "recommendation", "image", "data_export", "pipeline_run"]},
            "content": {"type": "string", "description": "Raw content. Base64 for image type, plain text for others."},
            "metadata": {"type": "object", "default": {}},
            "agent_id": {"type": "string"},
            "execution_id": {"type": "string"},
            "tier": {"type": "string", "enum": ["platform", "domain"], "default": "platform"},
            "kms_key_alias": {"type": "string"},
            "pipeline_date": {"type": "string"},
        },
        "required": ["type", "content"],
    },
))
async def _create_artifact(arguments: dict) -> dict:
    return await create_artifact(**arguments)


@mcp.tool(Tool(
    name="get_artifact",
    description="Retrieve artifact metadata and a signed URL (if ready).",
    inputSchema={"type": "object", "properties": {"artifact_id": {"type": "string"}}, "required": ["artifact_id"]},
))
async def _get_artifact(arguments: dict) -> dict:
    return await get_artifact(**arguments)


@mcp.tool(Tool(
    name="poll_artifact",
    description="Poll until the artifact is ready (or timeout). Returns signed URL when ready.",
    inputSchema={
        "type": "object",
        "properties": {
            "artifact_id": {"type": "string"},
            "timeout_s": {"type": "integer", "default": 60},
        },
        "required": ["artifact_id"],
    },
))
async def _poll_artifact(arguments: dict) -> dict:
    return await poll_artifact(**arguments)


@mcp.tool(Tool(
    name="list_artifacts",
    description="List artifacts with optional filters. Returns metadata only (no URLs).",
    inputSchema={
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["chart", "report", "simulation_result", "recommendation", "image", "data_export", "pipeline_run"]},
            "agent_id": {"type": "string"},
            "date": {"type": "string"},
            "limit": {"type": "integer", "default": 50},
            "execution_id": {"type": "string"},
        },
    },
))
async def _list_artifacts(arguments: dict) -> dict:
    return await list_artifacts(**arguments)


@mcp.tool(Tool(
    name="get_pipeline_run",
    description="Retrieve a pipeline run manifest by execution_id or date.",
    inputSchema={
        "type": "object",
        "properties": {
            "execution_id": {"type": "string"},
            "date": {"type": "string"},
        },
    },
))
async def _get_pipeline_run(arguments: dict) -> dict:
    execution_id = arguments.get("execution_id", "")
    date = arguments.get("date", "")
    catalog = ArtifactCatalog()
    storage = ArtifactStorage()

    if not execution_id and not date:
        return {"error": "At least one of execution_id or date is required"}

    entries = catalog.list_entries(
        artifact_type="pipeline_run",
        execution_id=execution_id if execution_id else None,
        date=date if date else None,
        limit=1,
    )
    if not entries:
        return {"error": "Pipeline run not found"}

    entry = entries[0]
    try:
        content = storage.get_object_bytes(entry["s3_key"]).decode("utf-8")
        manifest = json.loads(content)
    except Exception as e:
        manifest = {"error": f"Failed to fetch manifest: {e}"}

    return {
        "artifact_id": entry["artifact_id"],
        "execution_id": entry.get("execution_id", ""),
        "pipeline_date": entry.get("pipeline_date", ""),
        "created_at": entry.get("created_at", ""),
        "manifest": manifest,
    }


@mcp.tool(Tool(
    name="get_latest_run",
    description="Get the most recent pipeline run manifest.",
    inputSchema={"type": "object", "properties": {}},
))
async def _get_latest_run(arguments: dict) -> dict:
    catalog = ArtifactCatalog()
    storage = ArtifactStorage()

    entries = catalog.list_entries(artifact_type="pipeline_run", limit=1)
    if not entries:
        return {"error": "No pipeline runs found"}

    entry = entries[0]
    try:
        content = storage.get_object_bytes(entry["s3_key"]).decode("utf-8")
        manifest = json.loads(content)
    except Exception as e:
        manifest = {"error": f"Failed to fetch manifest: {e}"}

    return {
        "artifact_id": entry["artifact_id"],
        "execution_id": entry.get("execution_id", ""),
        "pipeline_date": entry.get("pipeline_date", ""),
        "created_at": entry.get("created_at", ""),
        "manifest": manifest,
    }


@mcp.tool(Tool(
    name="get_agent_result",
    description="Retrieve a specific agent's result artifact from a pipeline run.",
    inputSchema={
        "type": "object",
        "properties": {"execution_id": {"type": "string"}, "agent_id": {"type": "string"}},
        "required": ["execution_id", "agent_id"],
    },
))
async def _get_agent_result(arguments: dict) -> dict:
    catalog = ArtifactCatalog()
    storage = ArtifactStorage()

    entries = catalog.list_entries(
        execution_id=arguments["execution_id"],
        agent_id=arguments["agent_id"],
        limit=1,
    )
    if not entries:
        return {"error": f"No artifact found for agent {arguments['agent_id']} in execution {arguments['execution_id']}"}

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

    if entry.get("status") == "ready" and entry.get("type") in ("simulation_result", "recommendation", "pipeline_run", "data_export", "report"):
        try:
            raw = storage.get_object_bytes(entry["s3_key"]).decode("utf-8")
            result["content"] = json.loads(raw)
        except Exception:
            pass

    return result


@mcp.tool(Tool(
    name="search_artifacts",
    description="Search artifacts with date range, agent, type, and tier filters.",
    inputSchema={
        "type": "object",
        "properties": {
            "date_from": {"type": "string"}, "date_to": {"type": "string"},
            "agent_id": {"type": "string"}, "type": {"type": "string"},
            "tier": {"type": "string", "enum": ["platform", "domain"]},
            "limit": {"type": "integer", "default": 20},
        },
    },
))
async def _search_artifacts(arguments: dict) -> dict:
    catalog = ArtifactCatalog()
    storage = ArtifactStorage()

    date_from = arguments.get("date_from", "")
    date_to = arguments.get("date_to", "")
    agent_id = arguments.get("agent_id", "")
    artifact_type = arguments.get("type", "")
    tier = arguments.get("tier", "")
    limit = arguments.get("limit", 20)

    entries = catalog.list_entries(
        artifact_type=artifact_type or None,
        agent_id=agent_id or None,
        date=date_from or None,
        limit=limit,
    )

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
            "type": entry.get("type", ""), "agent_id": entry.get("agent_id", ""),
            "execution_id": entry.get("execution_id", ""),
            "tier": entry.get("tier", "platform"),
            "pipeline_date": entry.get("pipeline_date", ""),
            "status": entry.get("status", ""),
            "created_at": entry.get("created_at", ""),
            "signed_url": signed_url,
            "metadata": entry.get("metadata", {}),
        })

    return {"count": len(results), "artifacts": results}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
