"""Shared Pydantic schemas for agent-core."""

from __future__ import annotations

from agent_core.schemas.gateway_config import GatewayAuthType, GatewayConfig
from agent_core.schemas.identity_config import (
    AuthFlow,
    AuthorizerConfig,
    AuthorizerType,
    CredentialConfig,
    CredentialType,
    IdentityConfig,
)
from agent_core.schemas.memory_config import (
    MemoryConfig,
    MemoryStrategyConfig,
    MemoryStrategyType,
    RetrievalConfig,
)
from agent_core.schemas.tool_config import (
    BuiltinToolConfig,
    BuiltinToolType,
    McpToolConfig,
    ToolConfig,
    ToolDeclaration,
)

__all__ = [
    "AuthFlow",
    "AuthorizerConfig",
    "AuthorizerType",
    "BuiltinToolConfig",
    "BuiltinToolType",
    "CredentialConfig",
    "CredentialType",
    "GatewayAuthType",
    "GatewayConfig",
    "IdentityConfig",
    "McpToolConfig",
    "MemoryConfig",
    "MemoryStrategyConfig",
    "MemoryStrategyType",
    "RetrievalConfig",
    "ToolConfig",
    "ToolDeclaration",
]
