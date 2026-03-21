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

__all__ = [
    "AuthFlow",
    "AuthorizerConfig",
    "AuthorizerType",
    "CredentialConfig",
    "CredentialType",
    "GatewayAuthType",
    "GatewayConfig",
    "IdentityConfig",
]
