"""AgentCore Memory client wrapper.

Wraps ``bedrock_agentcore.memory.MemoryClient`` for event creation,
short-term history retrieval, and semantic memory search.
``bedrock_agentcore`` is a **hard dependency** — no fallback.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from bedrock_agentcore.memory import MemoryClient

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages interaction with the AgentCore Memory service.

    Provides:
    - ``create_memory_resource`` — provision a memory resource with strategies
    - ``create_event`` — persist conversation turns
    - ``get_last_k_turns`` — retrieve recent short-term history
    - ``retrieve_memories`` — semantic search across a namespace
    - ``create_memory_and_wait`` — extract and store a memory with a strategy
    """

    def __init__(
        self,
        region: str | None = None,
        memory_id: str | None = None,
        actor_id: str | None = None,
    ) -> None:
        self._region = (
            region
            or os.environ.get("AWS_DEFAULT_REGION")
            or os.environ.get("AWS_REGION")
        )
        if not self._region:
            raise RuntimeError(
                "No AWS region configured.  Pass region= or export AWS_DEFAULT_REGION."
            )
        self._memory_id = memory_id or os.environ.get("AGENTCORE_MEMORY_ID", "")
        self._actor_id = actor_id or os.environ.get("AGENTCORE_ACTOR_ID", "system")
        self._client = MemoryClient(region_name=self._region)

    @property
    def client(self) -> MemoryClient:
        """Raw AgentCore Memory client for advanced use cases."""
        return self._client

    def create_memory_resource(
        self,
        name: str,
        strategies: list[dict[str, Any]],
        event_expiry_days: int = 30,
        description: str = "",
    ) -> str:
        """Create a memory resource with extraction strategies.

        Returns the ``memory_id`` of the created resource.
        """
        strategy_configs = [
            {
                "strategyType": s["type"],
                "name": s["name"],
                "namespace": s["namespace"],
            }
            for s in strategies
        ]

        response = self._client.create_memory(
            name=name,
            description=description,
            strategies=strategy_configs,
            eventExpiryInDays=event_expiry_days,
        )
        memory_id = response["memoryId"]
        logger.info("Created memory resource %s (name=%s)", memory_id, name)
        return memory_id

    def create_event(
        self,
        memory_id: str,
        actor_id: str,
        session_id: str,
        messages: list[tuple[str, str]],
    ) -> None:
        """Store conversation turns as events.

        Args:
            memory_id: AgentCore memory resource ID.
            actor_id: The actor (user / agent) producing the event.
            session_id: Current session identifier.
            messages: List of ``(content, role)`` tuples to persist.
        """
        event_messages = [
            {"role": role, "content": content} for content, role in messages
        ]
        self._client.create_event(
            memoryId=memory_id,
            actorId=actor_id,
            sessionId=session_id,
            messages=event_messages,
        )
        logger.debug(
            "Persisted %d message(s) to memory %s / session %s",
            len(messages),
            memory_id,
            session_id,
        )

    def get_last_k_turns(
        self,
        memory_id: str,
        actor_id: str,
        session_id: str,
        k: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve the last *k* conversation turns from short-term memory.

        Returns list of event dicts ordered oldest-first.
        """
        response = self._client.get_events(
            memoryId=memory_id,
            actorId=actor_id,
            sessionId=session_id,
            maxResults=k,
        )
        events = response.get("events", [])
        logger.debug(
            "Retrieved %d turn(s) from memory %s / session %s",
            len(events),
            memory_id,
            session_id,
        )
        return events

    def retrieve_memories(
        self,
        memory_id: str,
        namespace: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search for extracted memories within a namespace.

        Returns list of memory dicts ranked by relevance.
        """
        response = self._client.retrieve_memories(
            memoryId=memory_id,
            namespace=namespace,
            query=query,
            maxResults=top_k,
        )
        memories = response.get("memories", [])
        logger.debug(
            "Retrieved %d memory(ies) from namespace '%s'",
            len(memories),
            namespace,
        )
        return memories

    def create_memory_and_wait(
        self,
        memory_id: str,
        content: str,
        strategy_name: str,
        namespace: str,
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Extract and store a memory, blocking until complete.

        Returns the created memory record.
        """
        kwargs: dict[str, Any] = {
            "memoryId": memory_id,
            "content": content,
            "strategyName": strategy_name,
            "namespace": namespace,
        }
        if ttl_seconds is not None:
            kwargs["ttlSeconds"] = ttl_seconds

        response = self._client.create_memory_and_wait(**kwargs)
        logger.info(
            "Created memory via strategy '%s' in namespace '%s'",
            strategy_name,
            namespace,
        )
        return response

    # ------------------------------------------------------------------
    # Session-oriented convenience methods (used by runtime/session.py)
    # ------------------------------------------------------------------

    def get_session_memory(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve recent conversation context for a session.

        Returns a dict with ``turns`` and ``session_id``, or ``None``
        if no history exists.
        """
        if not self._memory_id:
            logger.warning("No memory_id configured — cannot retrieve session memory")
            return None

        turns = self.get_last_k_turns(
            memory_id=self._memory_id,
            actor_id=self._actor_id,
            session_id=session_id,
        )
        if not turns:
            return None
        return {"session_id": session_id, "turns": turns}

    def update_session_memory(
        self,
        session_id: str,
        agent_id: str,
        updates: dict[str, Any],
    ) -> None:
        """Persist memory updates for a session.

        Converts the *updates* dict into a single event message.
        """
        if not self._memory_id:
            logger.warning("No memory_id configured — cannot persist session memory")
            return

        import json

        self.create_event(
            memory_id=self._memory_id,
            actor_id=agent_id,
            session_id=session_id,
            messages=[(json.dumps(updates), "assistant")],
        )

    def semantic_search(
        self,
        session_id: str,
        query: str,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search across extracted memories for a session.

        Uses the ``session_id`` as the namespace for scoping.
        """
        if not self._memory_id:
            logger.warning("No memory_id configured — cannot search memories")
            return []

        return self.retrieve_memories(
            memory_id=self._memory_id,
            namespace=session_id,
            query=query,
            top_k=max_results,
        )


def get_memory_manager() -> MemoryManager:
    """Factory function for creating a session-ready ``MemoryManager``.

    Reads configuration from environment variables:
      - ``AGENTCORE_MEMORY_ID`` (required)
      - ``AWS_DEFAULT_REGION`` / ``AWS_REGION``
      - ``AGENTCORE_ACTOR_ID`` (optional, defaults to ``"system"``)

    Raises:
        RuntimeError: If ``AGENTCORE_MEMORY_ID`` is not set.
    """
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID", "")
    if not memory_id:
        raise RuntimeError(
            "AGENTCORE_MEMORY_ID env var is not set.  "
            "Configure memory.memory_id in blueprint YAML."
        )
    return MemoryManager(memory_id=memory_id)
