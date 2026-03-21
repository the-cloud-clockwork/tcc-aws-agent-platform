"""Agent session — lifecycle manager for Strands Agent + MCP clients."""

from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from strands import Agent

    from agent_core.identity.wiring import IdentityWiring
    from agent_core.memory.wiring import MemoryWiring


class AgentSession:
    """Context manager wrapping an Agent + its MCP clients.

    Supports single-agent, Swarm, and Graph patterns via ``run()``.

    Usage::

        with loader.build_agent_session("my-agent") as session:
            result = session.run("Process dataset for item-A")
    """

    def __init__(
        self,
        agent: Agent,
        mcp_clients: list[Any],
        *,
        multi_agent: Any = None,
        pattern: str = "single",
        identity_wiring: IdentityWiring | None = None,
        memory_wiring: MemoryWiring | None = None,
    ) -> None:
        self.agent = agent
        self._mcp_clients = mcp_clients
        self.multi_agent = multi_agent
        self.pattern = pattern
        self._identity_wiring = identity_wiring
        self._memory_wiring = memory_wiring
        self._exit_stack = ExitStack()

    @property
    def identity(self) -> IdentityWiring | None:
        """Access identity wiring for credential decoration."""
        return self._identity_wiring

    @property
    def memory(self) -> MemoryWiring | None:
        """Access memory wiring for direct memory operations and branching."""
        return self._memory_wiring

    def run(self, prompt: str) -> Any:
        """Execute via the appropriate pattern (single, swarm, or graph)."""
        if self.multi_agent is not None:
            return self.multi_agent(prompt)
        return self.agent(prompt)

    def __enter__(self) -> AgentSession:
        # Strands MCPClient is lazily started on first tool call via the Agent.
        # We do NOT enter the MCP clients here — the Agent manages their lifecycle.
        # We only track them for cleanup in __exit__.
        return self

    def __exit__(self, *exc: Any) -> bool:
        # Clean up any MCP clients that were started by the Agent
        for client in self._mcp_clients:
            if getattr(client, "_tool_provider_started", False):
                try:
                    client.__exit__(None, None, None)
                except Exception:
                    pass
        return False
