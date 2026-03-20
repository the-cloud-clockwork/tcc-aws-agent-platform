"""Agent session — lifecycle manager for Strands Agent + MCP clients."""
from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from strands import Agent


class AgentSession:
    """Context manager wrapping an Agent + its MCP clients.

    Supports single-agent, Swarm, and Graph patterns via ``run()``.

    Usage::

        with loader.build_agent_session("gap-detector") as session:
            result = session.run("Analyze gaps for AAPL on 2026-03-15")
    """

    def __init__(
        self,
        agent: Agent,
        mcp_clients: list[Any],
        *,
        multi_agent: Any = None,
        pattern: str = "single",
    ) -> None:
        self.agent = agent
        self._mcp_clients = mcp_clients
        self.multi_agent = multi_agent
        self.pattern = pattern
        self._exit_stack = ExitStack()

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
