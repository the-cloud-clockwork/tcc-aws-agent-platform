"""Runtime adapter: translates between Lambda event and AgentCore payload.

This abstraction allows the same handler logic to work in both Lambda and
AgentCore Runtime environments.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class RuntimeMode(StrEnum):
    LAMBDA = "lambda"
    AGENTCORE = "agentcore"


@dataclass
class AgentPayload:
    """Normalized payload from either Lambda or AgentCore."""
    agent_id: str
    session_id: str
    execution_mode: str
    parameters: dict[str, Any] = field(default_factory=dict)
    memory_context: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Normalized result for either Lambda or AgentCore."""
    status: str
    agent_id: str
    session_id: str
    output: dict[str, Any] = field(default_factory=dict)
    claim_check: bool = False
    artifact_id: str | None = None
    memory_updates: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_lambda_response(self) -> dict[str, Any]:
        if self.status == "error":
            return {"statusCode": 500, "body": json.dumps({"error": self.error})}
        body = {**self.output}
        if self.claim_check:
            body = {
                "claim_check": True,
                "artifact_id": self.artifact_id,
                "message": "Output exceeded 256KB. Full result stored as artifact.",
            }
        if self.memory_updates:
            body["_memory_updates"] = self.memory_updates
        return {"statusCode": 200, "body": json.dumps(body)}

    def to_agentcore_response(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "output": self.output if not self.claim_check else {
                "claim_check": True, "artifact_id": self.artifact_id,
            },
            "memory_updates": self.memory_updates,
            "error": self.error,
        }


def get_runtime_mode() -> RuntimeMode:
    mode = os.environ.get("RUNTIME_MODE", "lambda").lower()
    try:
        return RuntimeMode(mode)
    except ValueError:
        logger.warning("Unknown RUNTIME_MODE '%s', defaulting to lambda", mode)
        return RuntimeMode.LAMBDA


def normalize_lambda_event(event: dict[str, Any]) -> AgentPayload:
    agent_id = event.get("agent_id", "unknown")
    session_id = event.get("session_id", _generate_session_id())
    execution_mode = event.get("execution_mode", os.environ.get("EXECUTION_MODE", "simulation"))
    reserved_keys = {"agent_id", "session_id", "execution_mode"}
    parameters = {k: v for k, v in event.items() if k not in reserved_keys}
    return AgentPayload(
        agent_id=agent_id, session_id=session_id, execution_mode=execution_mode,
        parameters=parameters, metadata={"source": "lambda", "runtime_mode": RuntimeMode.LAMBDA.value},
    )


def normalize_agentcore_payload(payload: dict[str, Any]) -> AgentPayload:
    inner = payload.get("payload", payload)
    session = payload.get("session", {})
    context = payload.get("context", {})
    agent_id = inner.get("agent_id", "unknown")
    session_id = inner.get("session_id") or session.get("session_id") or _generate_session_id()
    execution_mode = context.get("execution_mode") or inner.get("execution_mode") or os.environ.get("EXECUTION_MODE", "simulation")
    parameters = inner.get("parameters", {})
    memory_context = session.get("memory")
    return AgentPayload(
        agent_id=agent_id, session_id=session_id, execution_mode=execution_mode,
        parameters=parameters, memory_context=memory_context,
        metadata={"source": "agentcore", "runtime_mode": RuntimeMode.AGENTCORE.value, "identity": context.get("identity")},
    )


def normalize_payload(event_or_payload: dict[str, Any]) -> AgentPayload:
    """Auto-detect and normalize either Lambda event or AgentCore payload."""
    if "payload" in event_or_payload and isinstance(event_or_payload["payload"], dict):
        return normalize_agentcore_payload(event_or_payload)
    if "session" in event_or_payload and isinstance(event_or_payload["session"], dict):
        return normalize_agentcore_payload(event_or_payload)
    return normalize_lambda_event(event_or_payload)


def _generate_session_id() -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"session-{ts}-{uuid.uuid4().hex[:8]}"
