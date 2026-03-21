"""Remote agent tool factory.

Creates Strands ``@tool`` functions that wrap A2A client calls. The
coordinator agent sees remote specialists as regular tools.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_core.a2a.client import A2AClient

logger = logging.getLogger(__name__)


def remote_agent_tool(
    *,
    node_id: str,
    name: str,
    description: str,
    a2a_client: A2AClient,
    a2a_url: str = "",
    runtime_arn: str = "",
) -> Any:
    """Create a Strands ``@tool`` function that calls a remote agent.

    The generated tool accepts a ``query`` string parameter, calls the
    remote agent via A2A protocol or direct invoke, and returns the
    response text.

    Args:
        node_id: Node identifier for logging.
        name: Tool name visible to the agent.
        description: Tool description for the agent's tool schema.
        a2a_client: Shared A2AClient instance.
        a2a_url: A2A protocol URL. Takes priority over runtime_arn.
        runtime_arn: AgentCore Runtime ARN for direct invoke fallback.

    Returns:
        A decorated tool function compatible with Strands Agent.
    """
    from strands import tool

    @tool(name=name, description=description)
    def _call_remote_agent(query: str) -> str:
        """Send a query to a remote specialist agent and return the response."""
        if a2a_url:
            logger.info("Calling remote agent '%s' via A2A at %s", node_id, a2a_url)
            return a2a_client.call_a2a(a2a_url, query)
        if runtime_arn:
            logger.info("Calling remote agent '%s' via direct invoke", node_id)
            return a2a_client.call_direct(runtime_arn, {"prompt": query})
        msg = f"Node '{node_id}': neither a2a_url nor runtime_arn configured"
        raise ValueError(msg)

    return _call_remote_agent
