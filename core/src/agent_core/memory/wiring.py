"""Memory wiring — bridges blueprint config to runtime memory components.

Created once per :meth:`BlueprintLoader.build_agent_session` call when the
blueprint declares ``memory.strategies``.  Follows the same pattern as
:class:`~agent_core.identity.wiring.IdentityWiring`.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_core.memory.branching import MemoryBranchManager
from agent_core.memory.hook_provider import MemoryHookProvider
from agent_core.memory.manager import MemoryManager
from agent_core.schemas.memory_config import MemoryConfig

logger = logging.getLogger(__name__)


class MemoryWiring:
    """Orchestrates all memory components from a single ``MemoryConfig``.

    Exposes:
    - ``manager`` — direct API access to AgentCore Memory
    - ``hook_provider`` — Strands HookProvider for auto-persistence
    - ``branching`` — multi-agent memory branching
    - ``get_tool_provider_tools()`` — memory-as-tools (when enabled)
    """

    def __init__(
        self,
        config: MemoryConfig,
        memory_id: str,
        region: str | None = None,
    ) -> None:
        self._config = config
        self._memory_id = memory_id
        self._manager = MemoryManager(region=region)

        self._hook_provider = MemoryHookProvider(
            memory_manager=self._manager,
            memory_id=memory_id,
            config=config,
            retrieval_configs=list(config.retrieval),
        )

        self._branching = MemoryBranchManager(
            memory_id=memory_id,
            region=region,
        )

        if config.enable_tool_provider:
            logger.info("Memory tool provider enabled for memory_id=%s", memory_id)

    @property
    def config(self) -> MemoryConfig:
        return self._config

    @property
    def manager(self) -> MemoryManager:
        return self._manager

    @property
    def hook_provider(self) -> MemoryHookProvider:
        return self._hook_provider

    @property
    def branching(self) -> MemoryBranchManager:
        return self._branching

    @property
    def memory_id(self) -> str:
        return self._memory_id

    def get_tool_provider_tools(
        self,
        actor_id: str,
        session_id: str,
        namespace: str = "",
    ) -> list[Any]:
        """Create memory tools scoped to the given actor/session.

        Returns an empty list when ``enable_tool_provider`` is ``False``.
        """
        if not self._config.enable_tool_provider:
            return []
        from agent_core.memory.tool_provider import MemoryToolProvider

        provider = MemoryToolProvider(
            memory_id=self._memory_id,
            actor_id=actor_id,
            session_id=session_id,
            namespace=namespace,
        )
        return provider.tools
