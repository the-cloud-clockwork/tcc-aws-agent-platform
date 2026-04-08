"""AgentBlueprint Pydantic model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_core.schemas.execution_modes import ExecutionModes
from agent_core.schemas.evaluation_config import EvaluationConfig
from agent_core.schemas.gateway_config import GatewayConfig
from agent_core.schemas.identity_config import IdentityConfig
from agent_core.schemas.memory_config import MemoryConfig
from agent_core.schemas.model_config import ModelConfig
from agent_core.schemas.observability_config import ObservabilityConfig
from agent_core.schemas.policy_config import PolicyConfig
from agent_core.schemas.runtime_config import RuntimeConfig
from agent_core.schemas.tool_config import ToolDeclaration


class GraphNodeConfig(BaseModel):
    """A node in a multi-blueprint graph, referencing another agent blueprint.

    For agent nodes: agent_ref and node_id are needed.
    For gate nodes: type="gate" with trip_condition; agent_ref is None.
    For remote nodes: set a2a_url/a2a_url_env or runtime_arn/runtime_arn_env.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_ref: str | None = Field(
        default=None,
        description="Blueprint ID to load for this node. None for gate nodes.",
    )
    node_id: str = Field(..., description="Unique node identifier within the graph.")
    type: Literal["agent", "gate"] = Field(
        default="agent",
        description="Node type: 'agent' runs a blueprint, 'gate' evaluates a condition.",
    )
    a2a_url: str = Field(
        default="",
        description="A2A protocol URL for remote agent. Empty = in-process node.",
    )
    a2a_url_env: str = Field(
        default="",
        description="Env var name holding the A2A URL.",
    )
    runtime_arn: str = Field(
        default="",
        description="AgentCore Runtime ARN for direct invoke.",
    )
    runtime_arn_env: str = Field(
        default="",
        description="Env var name holding the runtime ARN.",
    )
    trip_condition: str | None = Field(
        default=None,
        description="Condition expression that gates execution (gate nodes only).",
    )
    fallback: str | None = Field(
        default=None,
        description="Node ID to route to when trip_condition is not met.",
    )


class GraphEdgeConfig(BaseModel):
    """An edge connecting two nodes in a multi-blueprint graph."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_node: str = Field(..., description="Source node ID.")
    to_node: str = Field(..., description="Destination node ID.")
    condition: str | None = Field(
        default=None,
        description="Safe expression ('field op value') or None for unconditional.",
    )


class MultiAgentConfig(BaseModel):
    """Multi-agent orchestration settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["coordinator", "specialist", "standalone"] = Field(
        default="standalone",
        description=(
            "coordinator calls remote agents, specialist exposes A2A server, "
            "standalone is in-process only."
        ),
    )
    pattern: Literal["swarm", "graph"] = Field(
        default="swarm",
        description="Orchestration pattern: 'swarm' or 'graph'.",
    )
    execution_timeout: int = Field(default=90, gt=0)
    node_timeout: int = Field(default=30, gt=0)
    max_handoffs: int = Field(default=20, gt=0)
    nodes: list[GraphNodeConfig] = Field(default_factory=list)
    edges: list[GraphEdgeConfig] = Field(default_factory=list)
    max_iterations: int = Field(default=20, gt=0)
    max_node_executions: int | None = Field(default=None)
    entry_point: str | None = Field(
        default=None,
        description="Node ID to start execution from (must be in nodes).",
    )
    specialists: list[str] = Field(
        default_factory=list,
        description="Blueprint IDs for specialist agents in swarm pattern.",
    )

    @model_validator(mode="after")
    def _validate_graph_refs(self) -> MultiAgentConfig:
        """Validate that edges and entry_point reference declared node IDs."""
        if not self.nodes:
            return self
        node_ids = {n.node_id for n in self.nodes}
        for edge in self.edges:
            if edge.from_node not in node_ids:
                raise ValueError(
                    f"Edge from_node '{edge.from_node}' not in declared nodes: {node_ids}"
                )
            if edge.to_node not in node_ids:
                raise ValueError(
                    f"Edge to_node '{edge.to_node}' not in declared nodes: {node_ids}"
                )
        if self.entry_point is not None and self.entry_point not in node_ids:
            raise ValueError(
                f"entry_point '{self.entry_point}' not in declared nodes: {node_ids}"
            )
        return self


class ArtifactConfig(BaseModel):
    """Configuration for mandatory artifact storage."""

    model_config = ConfigDict(frozen=True)

    tier: Literal["platform", "domain"] = "platform"
    kms_key_alias: str | None = None
    type: str = "report"


class ThinkingConfig(BaseModel):
    """Extended thinking configuration for agents that need deeper reasoning."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    budget_tokens: int = 10000


class AgentBlueprint(BaseModel):
    """Full specification for a single agent, loaded from YAML."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    version: str
    name: str
    description: str = ""
    model: ModelConfig
    prompt_ref: str = Field(
        ...,
        description="Reference key for the Prompt Registry (e.g. 'my_agent_v1.2').",
    )
    tools: list[ToolDeclaration] = Field(default_factory=list)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    policy: PolicyConfig | None = Field(
        default=None, description="Cedar access control configuration."
    )
    execution_modes: ExecutionModes = Field(default_factory=ExecutionModes)
    output_schema: str | None = Field(
        default=None,
        description="Name of the output schema (e.g. 'data_analysis_output_v1').",
    )
    hooks: list[str] = Field(default_factory=list)
    multi_agent: MultiAgentConfig | None = None
    tags: list[str] = Field(default_factory=list)
    thinking: ThinkingConfig | None = None
    artifacts: ArtifactConfig = Field(default_factory=ArtifactConfig)


AgentBlueprint.model_rebuild()
