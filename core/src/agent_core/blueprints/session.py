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

_NODE_TEXT_CAP = 8000


def _build_synthesis_prompt(original_prompt: str, graph_result: Any) -> str:
    """Format graph results into a coordinator synthesis prompt."""
    parts: list[str] = []
    results = getattr(graph_result, "results", None) or {}
    for node_id, node_result in results.items():
        node_texts: list[str] = []
        for ar in node_result.get_agent_results():
            text = str(ar)
            if len(text) > _NODE_TEXT_CAP:
                text = text[:_NODE_TEXT_CAP] + "\n... (truncated)"
            node_texts.append(text)
        parts.append(f"[{node_id}]\n" + "\n".join(node_texts))

    node_section = "\n\n".join(parts) if parts else "(no node outputs)"

    return (
        "The specialist analysis nodes have completed. Below are their outputs.\n\n"
        f"Original request:\n{original_prompt}\n\n"
        f"--- Node Results ---\n\n{node_section}\n\n---\n\n"
        "Based on the above analysis, proceed with strategy evaluation: "
        "match trading strategies to the confirmed signals, run run_backtest "
        "for the highest-conviction match, then call create_artifact with "
        "the complete output JSON. "
        "Your final turn MUST be exactly one create_artifact tool call."
    )


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
        role: str = "standalone",
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
        self.role = role
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
            graph_result = self.multi_agent(prompt)
            if self.role == "coordinator" and self.pattern == "graph":
                return self._run_synthesis_turn(prompt, graph_result)
            return graph_result
        return self.agent(prompt)

    def _run_synthesis_turn(self, original_prompt: str, graph_result: Any) -> Any:
        """Run the coordinator agent after graph nodes complete."""
        from strands.multiagent.base import Status

        if graph_result.status in (Status.FAILED, Status.INTERRUPTED):
            logger.warning(
                "Graph ended with status=%s — skipping coordinator synthesis turn",
                graph_result.status.value,
            )
            return graph_result

        synthesis_prompt = _build_synthesis_prompt(original_prompt, graph_result)
        logger.info(
            "Running coordinator synthesis turn (%d chars prompt)",
            len(synthesis_prompt),
        )
        try:
            return self.agent(synthesis_prompt)
        except Exception:
            logger.exception(
                "Coordinator synthesis turn failed — returning graph result as fallback"
            )
            return graph_result

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
            if self.role == "coordinator" and self.pattern == "graph":
                async for event in self._stream_synthesis_async(prompt):
                    yield event
                return
            async for event in self.multi_agent.stream_async(prompt):
                yield event
        elif hasattr(self.agent, "stream_async"):
            async for event in self.agent.stream_async(prompt):
                yield event
        else:
            result = self.run(prompt)
            yield result

    async def _stream_synthesis_async(self, prompt: str) -> AsyncIterator[Any]:
        """Stream graph events then coordinator synthesis events."""
        from strands.multiagent.base import Status

        graph_result = None
        async for event in self.multi_agent.stream_async(prompt):
            yield event
            if isinstance(event, dict) and "result" in event:
                graph_result = event["result"]

        if graph_result is None:
            logger.warning("Graph stream produced no result event — running sync fallback")
            try:
                graph_result = self.multi_agent(prompt)
            except Exception:
                logger.exception("Graph sync fallback failed")
                return

        if graph_result.status in (Status.FAILED, Status.INTERRUPTED):
            logger.warning(
                "Graph stream ended with status=%s — skipping synthesis",
                graph_result.status.value,
            )
            return

        synthesis_prompt = _build_synthesis_prompt(prompt, graph_result)
        logger.info("Streaming coordinator synthesis turn")
        try:
            if hasattr(self.agent, "stream_async"):
                async for event in self.agent.stream_async(synthesis_prompt):
                    yield event
            else:
                yield self.agent(synthesis_prompt)
        except Exception:
            logger.exception("Coordinator synthesis stream failed")

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
