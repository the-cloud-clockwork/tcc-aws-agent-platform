"""AgentCore Memory manager.

Wraps AgentCore Memory service with session management.
Provides three memory tiers:
- Short-term: within a single SFN execution (ephemeral)
- Long-term: cross-session preferences, strategy history (persistent)
- Episodic: retrievable by similarity search (indexed)

From CLAUDE.md:
  "AgentCore Memory (short/long/episodic tiers, semantic retrieval,
   cross-agent shared context)"
"""

from __future__ import annotations

import logging
import os
from datetime import UTC
from typing import Any

logger = logging.getLogger(__name__)

# Module-level singleton
_memory_manager: MemoryManager | None = None


class MemoryManager:
    """Unified memory manager for AgentCore Memory service.

    Usage:
        manager = MemoryManager()
        manager.update_session_memory(session_id, agent_id, {"key": "value"})
        data = manager.get_session_memory(session_id)
        results = manager.semantic_search(session_id, "AAPL gap analysis")
    """

    def __init__(
        self,
        region: str | None = None,
        memory_namespace: str | None = None,
    ) -> None:
        """Initialize AgentCore Memory manager.

        Args:
            region: AWS region for AgentCore Memory service.
            memory_namespace: Namespace prefix for memory keys (default: env-based).
        """
        self.region = region or os.environ.get("AWS_REGION", "eu-west-1")
        self.env_name = os.environ.get("ENV_NAME", "dev")
        _prefix = os.environ.get("PLATFORM_PREFIX", "agent")
        self.namespace = memory_namespace or f"{_prefix}-{self.env_name}"
        self._client = None

    @property
    def client(self) -> Any:
        """Lazy-initialize AgentCore Memory client."""
        if self._client is None:
            try:
                from bedrock_agentcore.memory import AgentCoreMemoryClient

                self._client = AgentCoreMemoryClient(
                    region=self.region,
                    namespace=self.namespace,
                )
                logger.info(
                    "AgentCore Memory client initialized: region=%s namespace=%s",
                    self.region,
                    self.namespace,
                )
            except ImportError:
                logger.warning(
                    "bedrock-agentcore-memory not available — "
                    "using in-memory fallback"
                )
                self._client = _InMemoryFallback()
        return self._client

    def get_session_memory(
        self,
        session_id: str,
        tier: str = "short_term",
    ) -> dict[str, Any] | None:
        """Retrieve memory for a session.

        Args:
            session_id: Session identifier (= SFN execution ID).
            tier: Memory tier — "short_term", "long_term", or "episodic".

        Returns:
            Memory dict or None if not found.
        """
        try:
            key = self._make_key(session_id, tier)
            result = self.client.get(key)
            if result:
                logger.debug(
                    "Retrieved %s memory for session %s: %d keys",
                    tier,
                    session_id,
                    len(result),
                )
            return result
        except Exception:
            logger.exception(
                "Failed to retrieve memory: session=%s tier=%s", session_id, tier
            )
            return None

    def update_session_memory(
        self,
        session_id: str,
        agent_id: str,
        updates: dict[str, Any],
        tier: str = "short_term",
    ) -> None:
        """Update memory for a session.

        Args:
            session_id: Session identifier.
            agent_id: Agent that produced the updates.
            updates: Key-value pairs to store.
            tier: Memory tier.
        """
        try:
            key = self._make_key(session_id, tier)
            self.client.update(
                key,
                {
                    **updates,
                    "_last_agent": agent_id,
                    "_updated_at": _now_iso(),
                },
            )
            logger.info(
                "Updated %s memory for session %s (agent=%s, %d keys)",
                tier,
                session_id,
                agent_id,
                len(updates),
            )
        except Exception:
            logger.exception(
                "Failed to update memory: session=%s agent=%s tier=%s",
                session_id,
                agent_id,
                tier,
            )

    def store_episodic(
        self,
        session_id: str,
        agent_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Store an episodic memory entry (indexed for semantic search).

        Args:
            session_id: Session identifier.
            agent_id: Agent that produced the content.
            content: Text content to index.
            metadata: Optional metadata (date, context, etc.).

        Returns:
            Memory entry ID or None on failure.
        """
        try:
            entry_id = self.client.store_episodic(
                namespace=self.namespace,
                session_id=session_id,
                agent_id=agent_id,
                content=content,
                metadata={
                    **(metadata or {}),
                    "execution_mode": os.environ.get("EXECUTION_MODE", "simulation"),
                    "stored_at": _now_iso(),
                },
            )
            logger.info(
                "Stored episodic memory: session=%s agent=%s entry=%s",
                session_id,
                agent_id,
                entry_id,
            )
            return entry_id
        except Exception:
            logger.exception("Failed to store episodic memory")
            return None

    def semantic_search(
        self,
        session_id: str | None = None,
        query: str = "",
        max_results: int = 5,
    ) -> dict[str, Any]:
        """Search episodic memory by semantic similarity.

        Args:
            session_id: Optional session filter.
            query: Natural language query.
            max_results: Maximum results.

        Returns:
            Search results dict with entries and scores.
        """
        try:
            results = self.client.search_episodic(
                namespace=self.namespace,
                query=query,
                session_id=session_id,
                max_results=max_results,
            )
            logger.info(
                "Semantic search '%s': %d results",
                query[:50],
                len(results.get("entries", [])),
            )
            return results
        except Exception:
            logger.exception("Semantic search failed")
            return {"entries": [], "query": query}

    def _make_key(self, session_id: str, tier: str) -> str:
        """Build a namespaced memory key."""
        return f"{self.namespace}/{tier}/{session_id}"


class _InMemoryFallback:
    """In-memory fallback when AgentCore Memory SDK is not available."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        self._episodic: list[dict[str, Any]] = []

    def get(self, key: str) -> dict[str, Any] | None:
        return self._store.get(key)

    def update(self, key: str, data: dict[str, Any]) -> None:
        if key not in self._store:
            self._store[key] = {}
        self._store[key].update(data)

    def store_episodic(self, **kwargs: Any) -> str:
        import uuid

        entry_id = uuid.uuid4().hex[:12]
        self._episodic.append({"id": entry_id, **kwargs})
        return entry_id

    def search_episodic(self, **kwargs: Any) -> dict[str, Any]:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 5)
        # Naive substring match fallback
        matches = [
            e
            for e in self._episodic
            if query.lower() in e.get("content", "").lower()
        ][:max_results]
        return {"entries": matches, "query": query}


def get_memory_manager() -> MemoryManager:
    """Get or create the module-level MemoryManager singleton."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()
