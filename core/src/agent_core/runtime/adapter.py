"""Runtime adapter: payload normalization for AgentCore Runtime.

All agents run on AgentCore Runtime. This module provides dataclasses
for normalized payloads and the InvocationContext that mirrors the
bedrock_agentcore.runtime context object.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class InvocationContext:
    """Context passed to @app.entrypoint handlers.

    Mirrors the bedrock_agentcore.runtime context object so handlers
    have a consistent interface whether called via the SDK or tests.
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    request_headers: dict[str, str] = field(default_factory=dict)
    agent_id: str = ""
    execution_mode: str = "simulation"


@dataclass
class AgentPayload:
    """Normalized payload for AgentCore Runtime invocations."""

    agent_id: str
    session_id: str
    execution_mode: str = "simulation"
    parameters: dict[str, Any] = field(default_factory=dict)
    memory_context: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Normalized result from an AgentCore Runtime invocation."""

    status: str
    agent_id: str
    session_id: str
    output: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        """Format as AgentCore Runtime response."""
        return {
            "status": self.status,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "output": self.output,
            "metadata": self.metadata,
        }


def normalize_payload(event: dict[str, Any]) -> AgentPayload:
    """Normalize an AgentCore Runtime event into AgentPayload.

    Extracts agent_id, session_id, execution_mode, and parameters
    from the incoming invocation payload.
    """
    agent_id = (
        event.get("agent_id")
        or event.get("agentId")
        or event.get("metadata", {}).get("agent_id", "default")
    )
    session_id = (
        event.get("session_id")
        or event.get("sessionId")
        or str(uuid.uuid4())
    )
    execution_mode = (
        event.get("execution_mode")
        or event.get("executionMode")
        or "simulation"
    )
    parameters = event.get("parameters") or event.get("params") or {}
    memory_context = event.get("memory_context")
    metadata = event.get("metadata", {})

    return AgentPayload(
        agent_id=agent_id,
        session_id=session_id,
        execution_mode=execution_mode,
        parameters=parameters,
        memory_context=memory_context,
        metadata=metadata,
    )
