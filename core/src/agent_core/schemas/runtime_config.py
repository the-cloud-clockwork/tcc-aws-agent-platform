"""RuntimeConfig schema -- agent runtime settings for AgentCore Runtime."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RuntimeConfig(BaseModel):
    """Runtime configuration for an agent on AgentCore Runtime.

    Maps to .bedrock_agentcore.yaml fields. All agents run on
    AgentCore Runtime (microVM per session, port 8080).
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["agentcore"] = "agentcore"
    max_iterations: int = Field(default=5, gt=0)
    max_execution_time: int = Field(
        default=120,
        gt=0,
        description="Maximum execution time in seconds.",
    )
    idle_timeout_minutes: int = Field(
        default=15,
        ge=1,
        description="Session idle timeout before microVM termination.",
    )
    network_mode: Literal["PUBLIC", "PRIVATE"] = Field(
        default="PUBLIC",
        description="PUBLIC for internet-facing, PRIVATE for VPC-only.",
    )
    protocol: Literal["HTTP", "MCP"] = Field(
        default="HTTP",
        description="HTTP for standard agents, MCP for hosted MCP servers.",
    )
    port: int = Field(
        default=8080,
        ge=1024,
        le=65535,
        description="Container listen port for /invocations and /ping.",
    )
    platform: Literal["linux/arm64", "linux/amd64"] = Field(
        default="linux/arm64",
        description="Container build architecture. ARM64 (Graviton) is required for AgentCore.",
    )
    observability_enabled: bool = Field(
        default=True,
        description="Enable OTEL auto-instrumentation via opentelemetry-instrument wrapper.",
    )
