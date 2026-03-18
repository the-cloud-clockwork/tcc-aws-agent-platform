"""ModelConfig schema -- provider-agnostic LLM configuration."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelConfig(BaseModel):
    """LLM model configuration extracted from agent blueprints."""

    model_config = ConfigDict(frozen=True)

    provider: Literal["bedrock", "anthropic", "litellm"] = "bedrock"
    model_id: str = Field(
        ...,
        description="Fully qualified model identifier, e.g. us.anthropic.claude-sonnet-4-20250514-v1:0",
    )
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, gt=0)
    cache_prompt: str | None = Field(
        default="default",
        description="Prompt caching strategy: 'default', 'none', or custom key.",
    )
    cache_tools: str | None = Field(
        default="default",
        description="Tool-result caching strategy.",
    )
