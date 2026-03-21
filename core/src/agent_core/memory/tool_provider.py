"""Expose memory recall/record as agent-callable tools.

When ``memory.enable_tool_provider: true`` in the blueprint, the agent
can explicitly call ``memory_recall`` and ``memory_record`` tools to
store and retrieve memories — in addition to the automatic hook-based
persistence provided by :class:`MemoryHookProvider`.
"""

from __future__ import annotations

import logging
from typing import Any

from strands_tools.agent_core_memory import (
    AgentCoreMemoryToolProvider as SdkToolProvider,
)

logger = logging.getLogger(__name__)


class MemoryToolProvider:
    """Wrapper around the Strands SDK memory tool provider."""

    def __init__(
        self,
        memory_id: str,
        actor_id: str,
        session_id: str,
        namespace: str = "",
    ) -> None:
        self._provider = SdkToolProvider(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id=session_id,
            namespace=namespace,
        )

    @property
    def tools(self) -> list[Any]:
        """Tool callables for injection into ``Agent(tools=[...])``.

        Returns ``memory_recall`` and ``memory_record`` tool functions.
        """
        return self._provider.tools
