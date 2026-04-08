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

    model_config = ConfigDict(frozen=True, extra="forbid")

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

    model_config = ConfigDict(frozen=True, extra="forbid")

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


class A2aToolConfig(BaseModel):
    """Declaration for an agent-to-agent (A2A) remote tool endpoint."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    a2a: str = Field(
        ...,
        description="Blueprint ID or URL of the remote A2A agent to invoke.",
    )


# Union type used in AgentBlueprint.tools — Pydantic v2 auto-discriminates
# because McpToolConfig requires ``mcp``, BuiltinToolConfig requires
# ``builtin``, and A2aToolConfig requires ``a2a``.
ToolDeclaration = Union[McpToolConfig, BuiltinToolConfig, A2aToolConfig]
