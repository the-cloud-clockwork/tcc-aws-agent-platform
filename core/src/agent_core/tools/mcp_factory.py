"""MCP client factory — create Strands MCPClient instances.

Provides proper Strands SDK MCPClient instantiation with streamable HTTP
transport. Each client is scoped per invocation via context manager.

Design rule:
  "MCP connections scoped per invocation — Always use with mcp_client:
   context managers in Lambda. Never reuse across warm invocations."
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)


def create_mcp_client(
    name: str,
    url: str,
    tool_filter: list[str] | None = None,
) -> MCPClient:
    """Create a Strands MCPClient with streamable HTTP transport.

    The returned client must be used as a context manager:
        with client:
            agent = Agent(tools=[client])

    Args:
        name: MCP server name (e.g., "my-mcp").
        url: Base URL of the MCP server (e.g., "http://localhost:8002").
        tool_filter: Optional list of tool names to expose. If provided,
            only these tools will be available from this MCP client.

    Returns:
        MCPClient instance configured with streamable HTTP transport.
    """
    mcp_url = url.rstrip("/") + "/mcp"

    kwargs: dict[str, Any] = {"prefix": name}
    if tool_filter:
        kwargs["tool_filters"] = {"allowed": tool_filter}

    client = MCPClient(
        lambda mcp_url=mcp_url: streamablehttp_client(mcp_url),  # type: ignore[misc]
        **kwargs,
    )
    logger.debug("Created MCP client '%s' -> %s (tools=%s)", name, mcp_url, tool_filter or "all")
    return client
