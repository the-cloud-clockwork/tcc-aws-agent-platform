"""Agent session — lifecycle manager for Strands Agent + MCP clients."""
from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from strands import Agent


class AgentSession:
    """Context manager wrapping an Agent + its MCP clients.

    Usage::

        with loader.build_agent_session("gap-detector") as session:
            result = session.agent("Analyze gaps for AAPL on 2026-03-15")
    """

    def __init__(self, agent: Agent, mcp_clients: list[Any]) -> None:
        self.agent = agent
        self._mcp_clients = mcp_clients
        self._exit_stack = ExitStack()

    def __enter__(self) -> AgentSession:
        for client in self._mcp_clients:
            self._exit_stack.enter_context(client)
        return self

    def __exit__(self, *exc: Any) -> bool:
        return self._exit_stack.__exit__(*exc)
