"""RuntimeConfig schema -- agent runtime settings."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RuntimeConfig(BaseModel):
    """Runtime configuration for an agent."""

    model_config = ConfigDict(frozen=True)

    type: Literal["agentcore", "lambda", "ecs"] = "agentcore"
    max_iterations: int = Field(default=5, gt=0)
    max_execution_time: int = Field(
        default=120,
        gt=0,
        description="Maximum execution time in seconds.",
    )
