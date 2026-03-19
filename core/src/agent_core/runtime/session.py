"""AgentCore session management.

Maps SFN execution IDs to AgentCore session IDs. Manages session lifecycle
(create, resume, close). Handles memory persistence across agent invocations
within the same SFN execution.

Design rule:
  "Session IDs map to SFN execution IDs — AgentCore Memory uses the same
   session_id convention."
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """In-memory session state for the current agent invocation.

    Attributes:
        session_id: Unique session identifier (= SFN execution ID).
        agent_id: Current agent within the session.
        execution_mode: backtest | paper | live.
        short_term: Ephemeral data for this SFN execution.
        memory_context: Prior context retrieved from AgentCore Memory.
        pending_updates: Memory updates to persist after agent completes.
    """

    session_id: str
    agent_id: str
    execution_mode: str
    short_term: dict[str, Any] = field(default_factory=dict)
    memory_context: dict[str, Any] | None = None
    pending_updates: dict[str, Any] = field(default_factory=dict)

    def store(self, key: str, value: Any) -> None:
        """Store a value in short-term session memory.

        Args:
            key: Memory key.
            value: Value to store (must be JSON-serializable).
        """
        self.short_term[key] = value
        self.pending_updates[key] = value
        logger.debug("Session %s: stored key '%s'", self.session_id, key)

    def retrieve(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from session memory.

        Checks short-term first, then falls back to memory_context
        (from AgentCore Memory long-term storage).

        Args:
            key: Memory key.
            default: Default value if key not found.

        Returns:
            Stored value or default.
        """
        if key in self.short_term:
            return self.short_term[key]
        if self.memory_context and key in self.memory_context:
            return self.memory_context[key]
        return default

    def get_pending_updates(self) -> dict[str, Any]:
        """Return all pending memory updates for persistence."""
        return dict(self.pending_updates)


class SessionManager:
    """Manages agent session lifecycle.

    In Lambda mode: sessions are DynamoDB-backed.
    In AgentCore mode: sessions are managed by AgentCore Memory service.

    This class abstracts the difference so agent handlers don't care.
    """

    def __init__(self, runtime_mode: str = "lambda") -> None:
        self.runtime_mode = runtime_mode
        self._agentcore_memory = None

    def create_session(
        self,
        session_id: str,
        agent_id: str,
        execution_mode: str,
        memory_context: dict[str, Any] | None = None,
    ) -> SessionState:
        """Create a new session state for an agent invocation.

        Args:
            session_id: Session ID (= SFN execution ID).
            agent_id: Agent identifier.
            execution_mode: backtest | paper | live.
            memory_context: Prior context from AgentCore Memory.

        Returns:
            Initialized SessionState.
        """
        logger.info(
            "Creating session: sid=%s agent=%s mode=%s runtime=%s",
            session_id,
            agent_id,
            execution_mode,
            self.runtime_mode,
        )

        session = SessionState(
            session_id=session_id,
            agent_id=agent_id,
            execution_mode=execution_mode,
            memory_context=memory_context,
        )

        if self.runtime_mode == "agentcore":
            self._init_agentcore_session(session)

        return session

    def persist_session(self, session: SessionState) -> None:
        """Persist session memory updates.

        In Lambda mode: writes to DynamoDB.
        In AgentCore mode: writes to AgentCore Memory service.

        Args:
            session: Session with pending updates.
        """
        updates = session.get_pending_updates()
        if not updates:
            logger.debug("Session %s: no updates to persist", session.session_id)
            return

        if self.runtime_mode == "agentcore":
            self._persist_agentcore_memory(session, updates)
        else:
            self._persist_dynamodb_memory(session, updates)

        logger.info(
            "Session %s: persisted %d memory updates",
            session.session_id,
            len(updates),
        )

    def retrieve_long_term(
        self,
        session_id: str,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Retrieve long-term memory for a session.

        In AgentCore mode, supports semantic search over episodic memory.

        Args:
            session_id: Session ID to retrieve memory for.
            query: Optional semantic query for episodic retrieval.

        Returns:
            Memory context dict.
        """
        if self.runtime_mode == "agentcore" and query:
            return self._semantic_retrieve(session_id, query)

        if self.runtime_mode == "agentcore":
            return self._get_agentcore_memory(session_id)

        return self._get_dynamodb_memory(session_id)

    def _init_agentcore_session(self, session: SessionState) -> None:
        """Initialize AgentCore Memory for this session."""
        try:
            from agent_core.memory.manager import get_memory_manager

            self._agentcore_memory = get_memory_manager()
            existing = self._agentcore_memory.get_session_memory(session.session_id)
            if existing:
                session.memory_context = existing
                logger.info(
                    "Session %s: loaded %d keys from AgentCore Memory",
                    session.session_id,
                    len(existing),
                )
        except ImportError:
            logger.warning("AgentCore Memory not available (agent_core.memory.manager not installed), falling back to local state")
        except Exception:
            logger.exception("Failed to initialize AgentCore Memory")

    def _persist_agentcore_memory(self, session: SessionState, updates: dict[str, Any]) -> None:
        """Write memory updates to AgentCore Memory service."""
        if self._agentcore_memory is None:
            logger.warning("AgentCore Memory not initialized, skipping persist")
            return

        try:
            self._agentcore_memory.update_session_memory(
                session_id=session.session_id,
                agent_id=session.agent_id,
                updates=updates,
            )
        except Exception:
            logger.exception("Failed to persist to AgentCore Memory")

    def _persist_dynamodb_memory(self, session: SessionState, updates: dict[str, Any]) -> None:
        """Write memory updates to DynamoDB (Lambda mode fallback)."""
        try:
            from datetime import datetime

            import boto3

            table_name = os.environ.get("SESSION_TABLE", "run_history")
            dynamodb = boto3.resource("dynamodb")
            table = dynamodb.Table(table_name)

            table.update_item(
                Key={"session_id": session.session_id},
                UpdateExpression="SET #mem = :mem, #ts = :ts, #agent = :agent",
                ExpressionAttributeNames={
                    "#mem": "memory_state",
                    "#ts": "updated_at",
                    "#agent": "last_agent_id",
                },
                ExpressionAttributeValues={
                    ":mem": updates,
                    ":ts": datetime.now(UTC).isoformat(),
                    ":agent": session.agent_id,
                },
            )
        except Exception:
            logger.exception("Failed to persist to DynamoDB")

    def _get_dynamodb_memory(self, session_id: str) -> dict[str, Any]:
        """Retrieve memory from DynamoDB."""
        try:
            import boto3

            table_name = os.environ.get("SESSION_TABLE", "run_history")
            dynamodb = boto3.resource("dynamodb")
            table = dynamodb.Table(table_name)

            response = table.get_item(Key={"session_id": session_id})
            item = response.get("Item", {})
            return item.get("memory_state", {})
        except Exception:
            logger.exception("Failed to retrieve from DynamoDB")
            return {}

    def _get_agentcore_memory(self, session_id: str) -> dict[str, Any]:
        """Retrieve memory from AgentCore Memory service."""
        if self._agentcore_memory is None:
            return {}
        try:
            return self._agentcore_memory.get_session_memory(session_id) or {}
        except Exception:
            logger.exception("Failed to retrieve from AgentCore Memory")
            return {}

    def _semantic_retrieve(self, session_id: str, query: str) -> dict[str, Any]:
        """Semantic search over episodic memory via AgentCore Memory."""
        if self._agentcore_memory is None:
            return {}
        try:
            return self._agentcore_memory.semantic_search(
                session_id=session_id,
                query=query,
                max_results=5,
            )
        except Exception:
            logger.exception("Semantic retrieval failed")
            return {}
