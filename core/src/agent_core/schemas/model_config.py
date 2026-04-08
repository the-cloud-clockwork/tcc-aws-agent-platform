"""ModelConfig schema -- provider-agnostic LLM configuration."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelConfig(BaseModel):
    """LLM model configuration extracted from agent blueprints."""

    model_config = ConfigDict(frozen=True)

    provider: Literal["bedrock", "anthropic", "litellm", "vertex"] = "bedrock"
    model_id: str = Field(
        ...,
        description="Fully qualified model identifier, e.g. us.anthropic.claude-sonnet-4-20250514-v1:0",
    )
    temperature: float = Field(..., ge=0.0, le=1.0, description="Sampling temperature.")
    max_tokens: int = Field(..., gt=0, description="Maximum output tokens.")
    cache_prompt: str | None = Field(
        default="default",
        description="Prompt caching policy: 'default', 'none', or custom key.",
    )
    cache_tools: str | None = Field(
        default="default",
        description="Tool-result caching policy.",
    )
    base_url: str | None = Field(
        default=None,
        description="API base URL for litellm/openai-compatible providers.",
    )
    api_key_env: str | None = Field(
        default=None,
        description="Env var name holding the API key. Never the key itself.",
    )
    extra_headers_env: dict[str, str] | None = Field(
        default=None,
        description="Map of HTTP header name → env var name. Resolved at runtime. E.g. {'CF-Access-Client-Id': 'CF_ACCESS_CLIENT_ID'}.",
    )
