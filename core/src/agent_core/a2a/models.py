"""A2A Protocol Pydantic models.

Pure data models for the A2A (Agent-to-Agent) protocol specification.
These are protocol-level models with no domain-specific logic.

Ref: https://google.github.io/A2A/specification/
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


# --- Agent Card models ---


class AgentSkill(BaseModel):
    """A skill (capability) exposed by the agent."""

    id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class AgentAuthentication(BaseModel):
    """Authentication requirements for the agent."""

    schemes: list[str] = Field(default_factory=lambda: ["bearer"])
    credentials: str | None = None  # URL to get credentials


class AgentCapabilities(BaseModel):
    """Agent capability declarations."""

    streaming: bool = False
    push_notifications: bool = False
    state_transition_history: bool = True


class AgentCard(BaseModel):
    """A2A Agent Card — the discovery document for an agent.

    Published at /.well-known/agent.json per the A2A specification.
    """

    name: str
    description: str
    url: str  # Agent endpoint URL
    version: str = "1.0.0"
    protocol_version: str = "0.2.1"  # A2A protocol version
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    authentication: AgentAuthentication = Field(default_factory=AgentAuthentication)
    default_input_modes: list[str] = Field(default_factory=lambda: ["application/json"])
    default_output_modes: list[str] = Field(default_factory=lambda: ["application/json"])
    skills: list[AgentSkill] = Field(default_factory=list)
    provider: dict[str, str] = Field(default_factory=dict)


# --- Task models ---


class TaskState(StrEnum):
    """A2A task states."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class TaskMessage(BaseModel):
    """A message in the A2A task conversation."""

    role: str  # "user" or "agent"
    parts: list[dict[str, Any]]  # Content parts (text, data, file, etc.)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TaskStatus(BaseModel):
    """Current status of an A2A task."""

    state: TaskState
    message: TaskMessage | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Task(BaseModel):
    """An A2A task representing a single request-response cycle."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None
    status: TaskStatus
    messages: list[TaskMessage] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
