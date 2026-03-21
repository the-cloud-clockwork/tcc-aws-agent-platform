"""ToolConfig schemas -- MCP and builtin tool declarations for agent blueprints."""

from __future__ import annotations

from enum import Enum
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class BuiltinToolType(str, Enum):
    """AWS-managed builtin tool types available through AgentCore."""

    CODE_INTERPRETER = "code_interpreter"
    BROWSER = "browser"


class McpToolConfig(BaseModel):
    """A single MCP tool-group declaration inside an agent blueprint."""

    model_config = ConfigDict(frozen=True)

    mcp: str = Field(..., description="MCP server name, e.g. 'data-mcp'.")
    tools: list[str] = Field(
        ...,
        min_length=1,
        description="List of tool names to expose from this MCP.",
    )


# Backward-compat alias — existing code imports ``ToolConfig``.
ToolConfig = McpToolConfig


class BuiltinToolConfig(BaseModel):
    """Declaration for an AWS-managed builtin tool (Code Interpreter, Browser).

    Region is optional here — when ``None``, the caller (BlueprintLoader)
    resolves it from the blueprint's gateway config or ``AWS_DEFAULT_REGION``.
    """

    model_config = ConfigDict(frozen=True)

    builtin: BuiltinToolType = Field(
        ...,
        description="Builtin tool type: 'code_interpreter' or 'browser'.",
    )
    region: str | None = Field(
        default=None,
        description="AWS region override.  Resolved from config/env when None.",
    )
    network_mode: Literal["PUBLIC", "PRIVATE"] = Field(
        default="PUBLIC",
        description="Network mode for the sandbox (Code Interpreter only).",
    )


# Union type used in AgentBlueprint.tools — Pydantic v2 auto-discriminates
# because McpToolConfig requires ``mcp`` while BuiltinToolConfig requires
# ``builtin``, and the two field sets are disjoint.
ToolDeclaration = Union[McpToolConfig, BuiltinToolConfig]
