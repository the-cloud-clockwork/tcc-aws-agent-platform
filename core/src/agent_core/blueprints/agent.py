"""AgentBlueprint Pydantic model."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_core.schemas.execution_modes import ExecutionModes
from agent_core.schemas.model_config import ModelConfig
from agent_core.schemas.runtime_config import RuntimeConfig
from agent_core.schemas.tool_config import ToolConfig


class MultiAgentConfig(BaseModel):
    """Multi-agent orchestration settings."""

    model_config = ConfigDict(frozen=True)

    pattern: Literal["swarm", "graph"] = Field(
        default="swarm",
        description="Orchestration pattern: 'swarm' or 'graph'.",
    )
    execution_timeout: int = Field(default=90, gt=0)
    node_timeout: int = Field(default=30, gt=0)
    max_handoffs: int = Field(default=20, gt=0)


class ThinkingConfig(BaseModel):
    """Extended thinking configuration for agents that need deeper reasoning."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    budget_tokens: int = 10000


class AgentBlueprint(BaseModel):
    """Full specification for a single agent, loaded from YAML."""

    model_config = ConfigDict(frozen=True)

    id: str
    version: str
    name: str
    description: str = ""
    model: ModelConfig
    prompt_ref: str = Field(
        ...,
        description="Reference key for the Prompt Registry (e.g. 'gap_detector_v1.2').",
    )
    tools: list[ToolConfig] = Field(default_factory=list)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    execution_modes: ExecutionModes = Field(default_factory=ExecutionModes)
    output_schema: str | None = Field(
        default=None,
        description="Name of the output schema (e.g. 'gap_detection_output_v1').",
    )
    hooks: list[str] = Field(default_factory=list)
    multi_agent: MultiAgentConfig | None = None
    tags: list[str] = Field(default_factory=list)
    thinking: ThinkingConfig | None = None


AgentBlueprint.model_rebuild()
