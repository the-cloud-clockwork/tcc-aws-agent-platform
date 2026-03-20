"""Semantic tool discovery via AgentCore Gateway.

Agents can discover tools dynamically using natural language queries instead
of hardcoded tool lists. The Gateway indexes all registered target tools and
supports semantic search across 10,000+ tools per target.

From CLAUDE.md:
  "Gateway provides semantic tool search — agents discover relevant tools dynamically"
  "Supports 10,000 tools per target with namespace prefixes"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agent_core.gateway.client import GatewayClient

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredTool:
    """A tool discovered via semantic search.

    Attributes:
        fqn: Fully qualified name (e.g., "data-mcp::get_data").
        target: Source target name.
        name: Tool name without namespace.
        description: Tool description.
        input_schema: JSON Schema for tool input.
        relevance_score: Semantic search relevance (0.0 to 1.0).
    """

    fqn: str
    target: str
    name: str
    description: str
    input_schema: dict[str, Any]
    relevance_score: float = 0.0


class ToolDiscovery:
    """Semantic tool discovery service.

    Usage:
        discovery = ToolDiscovery(gateway_client)
        tools = discovery.find_tools("retrieve time-series metrics for an entity")
        tools = discovery.find_tools_for_task("analyze data for ENTITY-1")
    """

    def __init__(self, gateway_client: GatewayClient) -> None:
        self.gateway = gateway_client

    def find_tools(
        self,
        query: str,
        max_results: int = 10,
        min_relevance: float = 0.3,
    ) -> list[DiscoveredTool]:
        """Find tools by semantic search.

        Args:
            query: Natural language description of what you need.
            max_results: Maximum number of results.
            min_relevance: Minimum relevance score threshold.

        Returns:
            List of DiscoveredTool objects, sorted by relevance.
        """
        raw_results = self.gateway.search_tools(query, max_results=max_results)

        tools = []
        for raw in raw_results:
            score = raw.get("relevance_score", 0.0)
            if score < min_relevance:
                continue

            tool = DiscoveredTool(
                fqn=raw.get("fqn", raw.get("name", "")),
                target=raw.get("target", ""),
                name=raw.get("name", ""),
                description=raw.get("description", ""),
                input_schema=raw.get("input_schema", {}),
                relevance_score=score,
            )
            tools.append(tool)

        tools.sort(key=lambda t: t.relevance_score, reverse=True)
        logger.info(
            "Tool discovery for '%s': %d results (min_relevance=%.2f)",
            query[:50],
            len(tools),
            min_relevance,
        )
        return tools

    def find_tools_for_task(
        self,
        task_description: str,
        agent_id: str | None = None,
        max_results: int = 20,
    ) -> list[DiscoveredTool]:
        """Find all tools relevant to a complex task.

        Higher-level than find_tools — decomposes a task description
        into multiple semantic queries to find a comprehensive tool set.

        Args:
            task_description: Full task description.
            agent_id: Optional agent ID for context-aware filtering.
            max_results: Maximum total results.

        Returns:
            Deduplicated list of relevant tools.
        """
        # Single semantic search for now — can be extended to multi-query
        tools = self.find_tools(task_description, max_results=max_results)

        if agent_id:
            # Filter tools the agent is allowed to use (pre-Cedar check)
            tools = [
                t for t in tools
                if self._agent_can_use(agent_id, t.fqn)
            ]

        return tools

    def list_all_tools(
        self,
        target: str | None = None,
    ) -> list[DiscoveredTool]:
        """List all available tools, optionally filtered by target.

        Args:
            target: Optional target name filter.

        Returns:
            List of all available tools.
        """
        raw_tools = self.gateway.list_tools(target=target)

        return [
            DiscoveredTool(
                fqn=raw.get("fqn", raw.get("name", "")),
                target=raw.get("target", ""),
                name=raw.get("name", ""),
                description=raw.get("description", ""),
                input_schema=raw.get("input_schema", {}),
            )
            for raw in raw_tools
        ]

    @staticmethod
    def _agent_can_use(agent_id: str, tool_fqn: str) -> bool:
        """Pre-check if an agent can use a tool.

        Tool access control is enforced by Cedar policies at the Gateway.
        This method is a no-op pass-through by default. Override in
        subclasses to add application-specific pre-filtering.

        Args:
            agent_id: Agent identifier.
            tool_fqn: Fully qualified tool name.

        Returns:
            True (always). Real enforcement is in Cedar policies.
        """
        return True
