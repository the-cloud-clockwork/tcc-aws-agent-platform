"""A2A Agent discovery — find and connect to external A2A agents.

Provides client-side discovery of external agents via the A2A protocol's
/.well-known/agent.json endpoint.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from agent_core.a2a.models import AgentCard

logger = logging.getLogger(__name__)


class DiscoveredAgent(BaseModel):
    """An externally discovered A2A agent."""

    card: AgentCard
    health_status: str = "unknown"  # "healthy", "degraded", "unhealthy", "unknown"
    last_checked: str | None = None


class AgentDiscovery:
    """Discover and cache external A2A agents.

    Discovery process:
    1. Fetch /.well-known/agent.json from known agent URLs
    2. Parse Agent Card
    3. Cache for reuse (TTL-based)
    4. Health check via ping
    """

    def __init__(self) -> None:
        self._cache: dict[str, DiscoveredAgent] = {}

    async def discover(self, agent_url: str) -> DiscoveredAgent | None:
        """Discover an agent by fetching its Agent Card.

        Args:
            agent_url: Base URL of the agent (e.g., https://agent.example.com).

        Returns:
            DiscoveredAgent if card found, None otherwise.
        """
        from datetime import UTC, datetime

        import httpx

        well_known_url = f"{agent_url.rstrip('/')}/.well-known/agent.json"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(well_known_url, timeout=10.0)
                response.raise_for_status()
                card_data = response.json()

            card = AgentCard(**card_data)

            discovered = DiscoveredAgent(
                card=card,
                health_status="healthy",
                last_checked=datetime.now(UTC).isoformat(),
            )
            self._cache[agent_url] = discovered

            logger.info("Discovered A2A agent: %s at %s", card.name, agent_url)
            return discovered

        except Exception as e:
            logger.warning("Failed to discover agent at %s: %s", agent_url, e)
            return None

    async def discover_many(self, urls: list[str]) -> list[DiscoveredAgent]:
        """Discover multiple agents in parallel."""
        import asyncio

        results = await asyncio.gather(
            *[self.discover(url) for url in urls],
            return_exceptions=True,
        )
        return [r for r in results if isinstance(r, DiscoveredAgent)]

    def get_cached(self, agent_url: str) -> DiscoveredAgent | None:
        """Get a cached agent discovery result."""
        return self._cache.get(agent_url)

    def list_cached(self) -> list[DiscoveredAgent]:
        """List all cached discovered agents."""
        return list(self._cache.values())

    def find_by_skill(self, skill_tag: str) -> list[DiscoveredAgent]:
        """Find cached agents that have a skill matching the given tag."""
        matches = []
        for agent in self._cache.values():
            for skill in agent.card.skills:
                if skill_tag in skill.tags:
                    matches.append(agent)
                    break
        return matches
