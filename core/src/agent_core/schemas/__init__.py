"""Shared Pydantic schemas for agent-core."""
from __future__ import annotations

from agent_core.schemas.gateway_config import GatewayAuthType, GatewayConfig

__all__ = [
    "GatewayAuthType",
    "GatewayConfig",
]
