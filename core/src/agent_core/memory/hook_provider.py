"""Strands HookProvider for automatic memory persistence and context loading.

Handles two lifecycle events:
- ``AgentInitializedEvent`` — load last K turns + semantic memories into system prompt
- ``MessageAddedEvent`` — persist each turn via ``create_event()``

Created by :class:`MemoryWiring` and injected into the Strands Agent ``hooks=[]``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agent_core.memory.manager import MemoryManager
from agent_core.schemas.memory_config import MemoryConfig, RetrievalConfig

if TYPE_CHECKING:
    from strands.hooks import HookRegistry

logger = logging.getLogger(__name__)


@dataclass
class MemoryHookProvider:
    """Strands-compatible hook provider for AgentCore Memory.

    Automatically:
    1. Loads short-term history and long-term semantic memories on agent init.
    2. Persists each conversation turn as events.
    """

    memory_manager: MemoryManager
    memory_id: str
    config: MemoryConfig
    retrieval_configs: list[RetrievalConfig] = field(default_factory=list)

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register memory lifecycle callbacks with the Strands hook registry."""
        from strands.hooks.events import AgentInitializedEvent, MessageAddedEvent

        registry.add_callback(AgentInitializedEvent, self._on_agent_initialized)
        registry.add_callback(MessageAddedEvent, self._on_message_added)

    def _on_agent_initialized(self, event: Any) -> None:
        """Load short-term history + long-term semantic memories into system prompt."""
        agent_state = dict(getattr(event.agent, "state", {}))
        actor_id = agent_state.get("actor_id", "unknown")
        session_id = agent_state.get("session_id", "unknown")

        context_parts: list[str] = []

        turns = self._load_short_term(actor_id, session_id)
        if turns:
            context_parts.append(self._format_turns(turns))

        memories = self._load_long_term(actor_id, session_id, event)
        if memories:
            context_parts.append(self._format_memories(memories))

        if context_parts:
            context_block = (
                "\n\n<memory_context>\n"
                + "\n".join(context_parts)
                + "\n</memory_context>"
            )
            event.agent.system_prompt += context_block
            logger.info(
                "Injected memory context (%d turns, %d memories) for session %s",
                len(turns),
                len(memories),
                session_id,
            )

    def _on_message_added(self, event: Any) -> None:
        """Persist the latest conversation turn."""
        messages = getattr(event.agent, "messages", [])
        if not messages:
            return

        last = dict(messages[-1]) if hasattr(messages[-1], "keys") else messages[-1]
        role = last.get("role", "user")
        content_blocks = last.get("content", [])
        text = _extract_text(content_blocks)
        if not text:
            return

        agent_state = dict(getattr(event.agent, "state", {}))
        actor_id = agent_state.get("actor_id", "unknown")
        session_id = agent_state.get("session_id", "unknown")

        try:
            self.memory_manager.create_event(
                memory_id=self.memory_id,
                actor_id=actor_id,
                session_id=session_id,
                messages=[(text, role)],
            )
        except Exception:
            logger.exception("Failed to persist turn for session %s", session_id)

    def _load_short_term(self, actor_id: str, session_id: str) -> list[dict[str, Any]]:
        """Load last K turns from short-term memory."""
        try:
            return self.memory_manager.get_last_k_turns(
                memory_id=self.memory_id,
                actor_id=actor_id,
                session_id=session_id,
                k=self.config.short_term_k,
            )
        except Exception:
            logger.exception(
                "Failed to load short-term memory for session %s", session_id
            )
            return []

    def _load_long_term(
        self, actor_id: str, session_id: str, event: Any
    ) -> list[dict[str, Any]]:
        """Retrieve semantic memories from configured namespaces."""
        query = _extract_query(event)
        if not query:
            return []

        all_memories: list[dict[str, Any]] = []
        for rc in self.retrieval_configs:
            namespace = rc.namespace.format(actorId=actor_id, sessionId=session_id)
            try:
                results = self.memory_manager.retrieve_memories(
                    memory_id=self.memory_id,
                    namespace=namespace,
                    query=query,
                    top_k=rc.top_k,
                )
                all_memories.extend(results)
            except Exception:
                logger.exception(
                    "Failed to retrieve memories from namespace '%s'", namespace
                )
        return all_memories

    @staticmethod
    def _format_turns(turns: list[dict[str, Any]]) -> str:
        """Format short-term turns for prompt injection."""
        lines = ["## Recent conversation history"]
        for turn in turns:
            msgs = turn.get("messages", [])
            for msg in msgs:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                lines.append(f"[{role}]: {content}")
        return "\n".join(lines)

    @staticmethod
    def _format_memories(memories: list[dict[str, Any]]) -> str:
        """Format long-term memories for prompt injection."""
        lines = ["## Relevant memories"]
        for mem in memories:
            content = mem.get("content", mem.get("text", ""))
            namespace = mem.get("namespace", "")
            if content:
                lines.append(f"- [{namespace}] {content}")
        return "\n".join(lines)


def _extract_text(content_blocks: Any) -> str:
    """Extract plain text from Strands message content blocks."""
    if isinstance(content_blocks, str):
        return content_blocks
    if isinstance(content_blocks, list):
        for block in content_blocks:
            if isinstance(block, dict) and "text" in block:
                return block["text"]
            if isinstance(block, str):
                return block
    return ""


def _extract_query(event: Any) -> str:
    """Extract a query string from the agent event for semantic retrieval."""
    messages = getattr(event.agent, "messages", [])
    for msg in reversed(messages):
        if msg.get("role") == "user":
            text = _extract_text(msg.get("content", []))
            if text:
                return text
    return ""
