"""Pydantic schemas for the ``memory:`` blueprint block."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MemoryStrategyType(str, Enum):
    """AgentCore Memory strategy types."""

    USER_PREFERENCE = "USER_PREFERENCE"
    SEMANTIC = "SEMANTIC"
    SUMMARY = "SUMMARY"
    EPISODIC = "EPISODIC"


class MemoryStrategyConfig(BaseModel):
    """A single memory extraction strategy."""

    model_config = ConfigDict(frozen=True)

    type: MemoryStrategyType
    name: str = Field(..., description="Human-readable strategy name.")
    namespace: str = Field(
        ...,
        description="Namespace template with {actorId}/{sessionId} placeholders.",
    )


class RetrievalConfig(BaseModel):
    """Configuration for a namespace to search during agent initialization."""

    model_config = ConfigDict(frozen=True)

    namespace: str = Field(..., description="Namespace template to retrieve from.")
    top_k: int = Field(default=5, ge=1, le=100)
    relevance_score: float = Field(default=0.3, ge=0.0, le=1.0)


class MemoryConfig(BaseModel):
    """Top-level ``memory:`` block in an agent blueprint.

    When ``strategies`` is non-empty the loader wires memory automatically.
    An empty list (the default) means no memory integration.
    """

    model_config = ConfigDict(frozen=True)

    strategies: list[MemoryStrategyConfig] = Field(default_factory=list)
    event_expiry_days: int = Field(default=30, ge=1, le=365)
    short_term_k: int = Field(default=5, ge=1, le=100)
    enable_tool_provider: bool = Field(
        default=False,
        description="Expose memory_recall and memory_record as agent-callable tools.",
    )
    retrieval: list[RetrievalConfig] = Field(
        default_factory=list,
        description="Namespaces to search during on_agent_initialized.",
    )
