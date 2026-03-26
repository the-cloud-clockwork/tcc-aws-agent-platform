"""Tool discovery via AgentCore Gateway.

Agents can discover tools by listing all available Gateway tools and
filtering by keyword matching.  The Gateway exposes tools from all
registered targets via a single MCP endpoint.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agent_core.gateway.client import GatewayClient

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredTool:
    """A tool discovered from the Gateway.

    Attributes:
        fqn: Fully qualified name (e.g., "order-tools::get_order").
        target: Source target name.
        name: Tool name without namespace.
        description: Tool description.
        input_schema: JSON Schema for tool input.
        relevance_score: Keyword match score (0.0 to 1.0).
    """

    fqn: str
    target: str
    name: str
    description: str
    input_schema: dict[str, Any]
    relevance_score: float = 0.0


class ToolDiscovery:
    """Tool discovery service backed by GatewayClient.

    Lists all tools from the Gateway's MCPClient and provides
    client-side keyword filtering.

    Usage::

        with GatewayClient(gateway_url="...") as gw:
            discovery = ToolDiscovery(gw)
            tools = discovery.find_tools("order management")
    """

    def __init__(self, gateway_client: GatewayClient) -> None:
        self.gateway = gateway_client

    def find_tools(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[DiscoveredTool]:
        """Find tools by keyword matching against names and descriptions.

        Args:
            query: Search keywords.
            max_results: Maximum number of results.

        Returns:
            List of DiscoveredTool objects sorted by relevance.
        """
        all_tools = self._list_raw_tools()
        query_lower = query.lower()
        query_terms = query_lower.split()

        scored: list[DiscoveredTool] = []
        for raw in all_tools:
            name = str(raw.get("name", ""))
            description = str(raw.get("description", ""))
            searchable = f"{name} {description}".lower()

            hits = sum(1 for term in query_terms if term in searchable)
            if hits == 0:
                continue

            score = hits / len(query_terms) if query_terms else 0.0
            fqn = name
            target = ""
            short_name = name
            if "::" in name:
                target, short_name = name.split("::", 1)

            scored.append(
                DiscoveredTool(
                    fqn=fqn,
                    target=target,
                    name=short_name,
                    description=description,
                    input_schema=raw.get("inputSchema", raw.get("input_schema", {})),
                    relevance_score=score,
                )
            )

        scored.sort(key=lambda t: t.relevance_score, reverse=True)
        logger.info("Tool discovery for '%s': %d results", query[:50], len(scored))
        return scored[:max_results]

    # Common English stop words filtered out during task-based tool discovery.
    _STOP_WORDS: frozenset[str] = frozenset(
        "a an the is are was were be been being have has had do does did "
        "will would shall should may might can could of in to for on with "
        "at by from as into through during before after above below between "
        "and or but not no nor so yet both either neither each every all "
        "any few more most other some such that this these those it its "
        "i me my we our you your he him his she her they them their what "
        "which who whom how when where why if then than too very just about "
        "also back only even still again further once here there up down "
        "out off over under need please get make use".split()
    )

    def find_tools_for_task(
        self,
        task_description: str,
        agent_id: str | None = None,
        max_results: int = 20,
    ) -> list[DiscoveredTool]:
        """Find tools relevant to a complex task using weighted scoring.

        Scoring strategy (no external dependencies):
          - **Name exact match** (weight 3.0): a query term matches a tool name
            segment exactly (split on ``_`` and ``-``).
          - **Description match** (weight 1.0): a query term appears anywhere in
            the tool description.
          - **Target context boost** (weight 2.0): if *agent_id* is provided and
            a query term matches a target name, the tool gets a bonus — useful
            when the caller already knows which target namespace is relevant.

        The final score is normalised against the number of query terms so that
        longer task descriptions don't inflate scores.

        Args:
            task_description: Full task description.
            agent_id: Optional agent ID for context-aware target boosting.
            max_results: Maximum total results.

        Returns:
            Deduplicated list of relevant tools sorted by score.
        """
        query_terms = [
            t
            for t in task_description.lower().split()
            if t not in self._STOP_WORDS and len(t) > 1
        ]
        if not query_terms:
            return self.find_tools(task_description, max_results=max_results)

        all_tools = self._list_raw_tools()
        scored: list[DiscoveredTool] = []

        for raw in all_tools:
            name = str(raw.get("name", ""))
            description = str(raw.get("description", ""))

            fqn = name
            target = ""
            short_name = name
            if "::" in name:
                target, short_name = name.split("::", 1)

            name_parts = set(short_name.lower().replace("-", "_").split("_"))
            desc_lower = description.lower()
            target_lower = target.lower()

            score = 0.0
            for term in query_terms:
                if term in name_parts:
                    score += 3.0
                if term in desc_lower:
                    score += 1.0
                if agent_id and term in target_lower:
                    score += 2.0

            if not score:
                continue

            normalised = score / len(query_terms)

            scored.append(
                DiscoveredTool(
                    fqn=fqn,
                    target=target,
                    name=short_name,
                    description=description,
                    input_schema=raw.get("inputSchema", raw.get("input_schema", {})),
                    relevance_score=round(normalised, 4),
                )
            )

        scored.sort(key=lambda t: t.relevance_score, reverse=True)
        logger.info(
            "Task-based tool discovery for '%s': %d results",
            task_description[:50],
            len(scored),
        )
        return scored[:max_results]

    def list_all_tools(self) -> list[DiscoveredTool]:
        """List all available tools from the Gateway."""
        raw_tools = self._list_raw_tools()

        result = []
        for raw in raw_tools:
            name = str(raw.get("name", ""))
            description = str(raw.get("description", ""))
            target = ""
            short_name = name
            if "::" in name:
                target, short_name = name.split("::", 1)

            result.append(
                DiscoveredTool(
                    fqn=name,
                    target=target,
                    name=short_name,
                    description=description,
                    input_schema=raw.get("inputSchema", raw.get("input_schema", {})),
                )
            )
        return result

    def _list_raw_tools(self) -> list[dict[str, Any]]:
        """Get raw tool dicts from the GatewayClient's MCPClient."""
        try:
            tools = self.gateway.list_tools_sync()
            return [
                t
                if isinstance(t, dict)
                else {
                    "name": getattr(t, "name", ""),
                    "description": getattr(t, "description", ""),
                    "inputSchema": getattr(t, "inputSchema", {}),
                }
                for t in tools
            ]
        except Exception:
            logger.exception("Failed to list tools from Gateway")
            return []
