"""Strands SessionManager bridge.

Adapts Strands SDK SessionManager ABC to agent_core.SessionState,
accumulating messages and agent state in-memory with explicit flush.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from strands.session.session_manager import SessionManager as StrandsSessionManager

from agent_core.runtime.session import SessionState

logger = logging.getLogger(__name__)

_MESSAGES_KEY = "strands_messages"
_AGENT_STATE_KEY = "strands_agent_state"
_MULTI_AGENT_KEY = "strands_multi_agent_state"


class StrandsSessionBridge(StrandsSessionManager):
    """Bridge between Strands SessionManager and agent_core SessionState.

    Accumulates messages and state during an invocation. The caller
    must call ``flush()`` after execution to persist accumulated state
    to the backing SessionState (which can then be written to DynamoDB).
    """

    def __init__(self, session_state: SessionState) -> None:
        self._state = session_state
        self._messages: list[dict[str, Any]] = []
        self._agent_state: dict[str, Any] = {}
        self._multi_agent_state: dict[str, Any] = {}

    def initialize(self, agent: Any, **kwargs: Any) -> None:
        """Restore prior messages from session state into the agent."""
        prior = self._state.retrieve(_MESSAGES_KEY)
        if prior and isinstance(prior, list):
            self._messages = copy.deepcopy(prior)
            if hasattr(agent, "messages") and isinstance(agent.messages, list):
                agent.messages.clear()
                agent.messages.extend(self._messages)
        logger.debug(
            "StrandsSessionBridge initialized with %d prior messages",
            len(self._messages),
        )

    def append_message(self, message: dict[str, Any], agent: Any, **kwargs: Any) -> None:
        """Accumulate a message from the agent conversation."""
        self._messages.append(copy.deepcopy(message))

    def sync_agent(self, agent: Any, **kwargs: Any) -> None:
        """Capture current agent state for later persistence."""
        state: dict[str, Any] = {}
        if hasattr(agent, "messages"):
            state["messages"] = copy.deepcopy(agent.messages)
        if hasattr(agent, "name"):
            state["agent_name"] = agent.name
        self._agent_state = state

    def redact_latest_message(self, redact_message: dict[str, Any], agent: Any, **kwargs: Any) -> None:
        """Replace the most recently appended message."""
        if self._messages:
            self._messages[-1] = copy.deepcopy(redact_message)

    def initialize_multi_agent(self, source: Any, **kwargs: Any) -> None:
        """No-op for multi-agent init -- handled by orchestrator."""
        logger.debug("StrandsSessionBridge: initialize_multi_agent (no-op)")

    def sync_multi_agent(self, source: Any, **kwargs: Any) -> None:
        """Capture orchestrator state (Swarm/Graph metadata)."""
        state: dict[str, Any] = {}
        if hasattr(source, "name"):
            state["orchestrator_name"] = source.name
        if hasattr(source, "current_agent") and hasattr(source.current_agent, "name"):
            state["current_agent"] = source.current_agent.name
        self._multi_agent_state = state

    def flush(self) -> None:
        """Write accumulated state to the backing SessionState.

        After calling this, the session state's pending_updates
        contain the Strands conversation data ready for DynamoDB persistence.
        """
        self._state.store(_MESSAGES_KEY, self._messages)
        if self._agent_state:
            self._state.store(_AGENT_STATE_KEY, self._agent_state)
        if self._multi_agent_state:
            self._state.store(_MULTI_AGENT_KEY, self._multi_agent_state)
        logger.debug(
            "StrandsSessionBridge flushed: %d messages, agent_state=%s, multi_agent=%s",
            len(self._messages),
            bool(self._agent_state),
            bool(self._multi_agent_state),
        )
