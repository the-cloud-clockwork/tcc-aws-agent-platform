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
        for client in self._mcp_clients:
            self._exit_stack.enter_context(client)
        return self

    def __exit__(self, *exc: Any) -> bool:
        return bool(self._exit_stack.__exit__(*exc))
