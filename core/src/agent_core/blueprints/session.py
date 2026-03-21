"""Agent session — lifecycle manager for Strands Agent + MCP clients."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import ExitStack
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from strands import Agent

    from agent_core.evaluation.wiring import EvaluationWiring
    from agent_core.policy.wiring import PolicyWiring
    from agent_core.hooks.observability_hooks import CompositeObservabilityHook
    from agent_core.identity.wiring import IdentityWiring
    from agent_core.memory.wiring import MemoryWiring
    from agent_core.runtime.strands_session_bridge import StrandsSessionBridge
    from agent_core.tools.wiring import BuiltinToolWiring

logger = logging.getLogger(__name__)


class AgentSession:
    """Context manager wrapping an Agent + its MCP clients.

    Supports single-agent, Swarm, and Graph patterns via ``run()``.
    Supports streaming via ``stream_async()``.
    Supports multi-turn conversation via ``run_turn()`` with session bridge.

    Usage::

        with loader.build_agent_session("my-agent") as session:
            result = session.run("Process dataset for item-A")

        # Streaming:
        with loader.build_agent_session("my-agent") as session:
            async for event in session.stream_async("Analyze data"):
                print(event)

        # Multi-turn:
        with loader.build_agent_session("my-agent") as session:
            session.run_turn("Hello")
            session.run_turn("What did I just say?")
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
        builtin_wiring: BuiltinToolWiring | None = None,
        evaluation_wiring: EvaluationWiring | None = None,
        policy_wiring: PolicyWiring | None = None,
        session_bridge: StrandsSessionBridge | None = None,
        observability_hook: CompositeObservabilityHook | None = None,
    ) -> None:
        self.agent = agent
        self._mcp_clients = mcp_clients
        self.multi_agent = multi_agent
        self.pattern = pattern
        self._identity_wiring = identity_wiring
        self._memory_wiring = memory_wiring
        self._builtin_wiring = builtin_wiring
        self._evaluation_wiring = evaluation_wiring
        self._policy_wiring = policy_wiring
        self._session_bridge = session_bridge
        self._observability_hook = observability_hook
        self._exit_stack = ExitStack()

    @property
    def identity(self) -> IdentityWiring | None:
        """Access identity wiring for credential decoration."""
        return self._identity_wiring

    @property
    def memory(self) -> MemoryWiring | None:
        """Access memory wiring for direct memory operations and branching."""
        return self._memory_wiring

    @property
    def builtin(self) -> BuiltinToolWiring | None:
        """Access builtin tool wiring for Code Interpreter / Browser."""
        return self._builtin_wiring

    @property
    def evaluation(self) -> EvaluationWiring | None:
        """Access evaluation wiring for on-demand scoring and result queries."""
        return self._evaluation_wiring

    @property
    def policy(self) -> PolicyWiring | None:
        """Access policy wiring for versioning and rollback."""
        return self._policy_wiring

    @property
    def observability(self) -> CompositeObservabilityHook | None:
        """Access the observability hook for cost/token summaries."""
        return self._observability_hook

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Access the current conversation message history."""
        if hasattr(self.agent, "messages"):
            return self.agent.messages
        return []

    def run(self, prompt: str) -> Any:
        """Execute via the appropriate pattern (single, swarm, or graph)."""
        if self.multi_agent is not None:
            return self.multi_agent(prompt)
        return self.agent(prompt)

    def run_turn(self, prompt: str) -> Any:
        """Execute a single turn in a multi-turn conversation.

        Unlike ``run()``, this preserves message history across calls
        within the same session. The Strands Agent accumulates messages
        internally; the session bridge syncs state after each turn.
        """
        result = self.run(prompt)
        if self._session_bridge is not None:
            self._session_bridge.sync_agent(self.agent)
        return result

    async def stream_async(self, prompt: str) -> AsyncIterator[Any]:
        """Stream agent response asynchronously.

        Yields events from the Strands Agent's ``stream_async()`` method.
        For multi-agent patterns, delegates to the orchestrator if it
        supports streaming, otherwise falls back to non-streaming.
        """
        if self.multi_agent is not None and hasattr(self.multi_agent, "stream_async"):
            async for event in self.multi_agent.stream_async(prompt):
                yield event
        elif hasattr(self.agent, "stream_async"):
            async for event in self.agent.stream_async(prompt):
                yield event
        else:
            result = self.run(prompt)
            yield result

    async def stream_turn_async(self, prompt: str) -> AsyncIterator[Any]:
        """Stream a single turn, preserving conversation history."""
        async for event in self.stream_async(prompt):
            yield event
        if self._session_bridge is not None:
            self._session_bridge.sync_agent(self.agent)

    def stream(self, prompt: str) -> Iterator[Any]:
        """Synchronous streaming wrapper.

        Runs the async stream in a new event loop. Prefer
        ``stream_async()`` when already in an async context.
        """
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            agen = self.stream_async(prompt)
            while True:
                try:
                    yield loop.run_until_complete(agen.__anext__())
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    def __enter__(self) -> AgentSession:
        # Start builtin tool providers that need explicit lifecycle
        if self._builtin_wiring is not None:
            self._builtin_wiring.start()
        # Initialize session bridge to restore prior messages
        if self._session_bridge is not None:
            self._session_bridge.initialize(self.agent)
        return self

    def __exit__(self, *exc: Any) -> bool:
        # Flush session bridge to persist accumulated state
        if self._session_bridge is not None:
            try:
                self._session_bridge.flush()
            except Exception:
                logger.debug("Session bridge flush failed -- non-fatal")
        # Stop builtin tool providers first
        if self._builtin_wiring is not None:
            try:
                self._builtin_wiring.stop()
            except Exception:
                pass
        # Clean up any MCP clients that were started by the Agent
        for client in self._mcp_clients:
            if getattr(client, "_tool_provider_started", False):
                try:
                    client.__exit__(None, None, None)
                except Exception:
                    pass
        return False
