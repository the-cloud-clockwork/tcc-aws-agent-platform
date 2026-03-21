"""Memory branching for multi-agent conversations.

Wraps ``bedrock_agentcore.memory.MemorySessionManager`` to provide
isolated memory contexts for sub-agents.  Each sub-agent writes to
its own branch; the coordinator can read from all branches.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from bedrock_agentcore.memory import MemorySessionManager

logger = logging.getLogger(__name__)


class MemoryBranchManager:
    """Manages conversation branching for multi-agent workflows.

    Wraps ``MemorySessionManager`` from the AgentCore SDK.
    """

    def __init__(
        self,
        memory_id: str,
        region: str | None = None,
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
        self._memory_id = memory_id
        self._manager = MemorySessionManager(
            memory_id=memory_id,
            region_name=self._region,
        )

    @property
    def memory_id(self) -> str:
        return self._memory_id

    def create_session(
        self,
        actor_id: str,
        session_id: str,
    ) -> Any:
        """Create a memory session for branching.

        Returns a session object that can be passed to ``fork_conversation``
        and ``list_branches``.
        """
        session = self._manager.create_memory_session(actor_id, session_id)
        logger.info(
            "Created memory session for actor=%s session=%s",
            actor_id,
            session_id,
        )
        return session

    def fork_conversation(
        self,
        session: Any,
        root_event_id: str,
        branch_name: str,
        messages: list[tuple[str, str]] | None = None,
    ) -> None:
        """Fork a conversation into a named branch for a sub-agent.

        Args:
            session: Session object from :meth:`create_session`.
            root_event_id: Event ID to branch from.
            branch_name: Human-readable branch identifier.
            messages: Optional seed messages as ``(content, role)`` tuples.
        """
        formatted = [
            {"role": role, "content": content} for content, role in (messages or [])
        ]
        session.fork_conversation(
            root_event_id=root_event_id,
            branch_name=branch_name,
            messages=formatted,
        )
        logger.info("Forked branch '%s' from event %s", branch_name, root_event_id)

    def get_branch_turns(
        self,
        session: Any,
        branch_name: str,
        k: int = 5,
    ) -> list[dict[str, Any]]:
        """Read the last *k* turns from a specific branch."""
        return session.get_last_k_turns(k=k, branch_name=branch_name)

    def list_branches(self, session: Any) -> list[str]:
        """List all branch names in a session."""
        return session.list_branches()
