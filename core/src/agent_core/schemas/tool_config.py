"""ToolConfig schema -- MCP tool declarations for agent blueprints."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ToolConfig(BaseModel):
    """A single MCP tool-group declaration inside an agent blueprint."""

    model_config = ConfigDict(frozen=True)

    mcp: str = Field(..., description="MCP server name, e.g. 'data-mcp'.")
    tools: list[str] = Field(
        ...,
        min_length=1,
        description="List of tool names to expose from this MCP.",
    )
