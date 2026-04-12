"""Lambda handler for AgentCore Gateway MCP tool dispatch.

Receives tool calls routed by the AgentCore Gateway (Lambda target) and
dispatches to the appropriate artifact tool function. Reuses the existing
``mcp_artifacts`` tool implementations.

The Gateway sends events shaped as::

    {
        "name": "create_artifact",
        "arguments": {"type": "report", "content": "...", ...}
    }

The handler returns a JSON dict that Gateway wraps in an MCP response.
"""

from __future__ import annotations

import asyncio
import json
import logging
import traceback

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Lazy-load tool functions to avoid import overhead on cold starts when
# only a subset of tools are called.
_TOOL_REGISTRY: dict | None = None


def _get_tool_registry() -> dict:
    global _TOOL_REGISTRY
    if _TOOL_REGISTRY is not None:
        return _TOOL_REGISTRY

    from mcp_artifacts.tools.create import create_artifact
    from mcp_artifacts.tools.get import get_artifact
    from mcp_artifacts.tools.list_artifacts import list_artifacts
    from mcp_artifacts.tools.poll import poll_artifact

    _TOOL_REGISTRY = {
        "create_artifact": create_artifact,
        "get_artifact": get_artifact,
        "list_artifacts": list_artifacts,
        "poll_artifact": poll_artifact,
    }
    return _TOOL_REGISTRY


def handler(event: dict, context) -> dict:
    """Lambda entry point for AgentCore Gateway tool calls.

    Two invocation formats:
    1. Direct: {"name": "create_artifact", "arguments": {...}}
    2. Gateway Lambda target: just the arguments dict (no "name" wrapper)
       — the Gateway resolves the tool name from the MCP prefix and passes
       only arguments. We infer the tool from the argument keys.
    """
    tool_name = event.get("name", "")
    arguments = event.get("arguments", {})

    if not tool_name and "name" not in event:
        # Gateway Lambda target format — arguments are the top-level event.
        # Infer tool from argument signature.
        if "content" in event:
            tool_name = "create_artifact"  # create_artifact validates `type` downstream
        elif "artifact_id" in event and "timeout_s" in event:
            tool_name = "poll_artifact"
        elif "artifact_id" in event:
            tool_name = "get_artifact"
        else:
            tool_name = "list_artifacts"
        arguments = event

    if isinstance(arguments, str):
        arguments = json.loads(arguments)

    registry = _get_tool_registry()
    tool_fn = registry.get(tool_name)

    if tool_fn is None:
        return {
            "error": "UnknownTool",
            "message": f"Tool '{tool_name}' is not registered. Available: {list(registry.keys())}",
        }

    try:
        result = tool_fn(**arguments)
        if asyncio.iscoroutine(result):
            result = asyncio.get_event_loop().run_until_complete(result)
        return result
    except Exception as exc:
        logger.exception("Tool %s failed", tool_name)
        return {
            "error": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
