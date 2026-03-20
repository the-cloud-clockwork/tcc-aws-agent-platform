"""Gateway subsystem — universal tool bridge via AgentCore Gateway."""
from agent_core.gateway.client import GatewayClient, GatewayConfigError, GatewayError, GatewayPolicyDeniedError
from agent_core.gateway.target_registry import (
    GatewayTarget,
    OutboundAuthType,
    TargetRegistry,
    TargetType,
)
from agent_core.gateway.tool_discovery import DiscoveredTool, ToolDiscovery

__all__ = [
    "DiscoveredTool",
    "GatewayClient",
    "GatewayConfigError",
    "GatewayError",
    "GatewayPolicyDeniedError",
    "GatewayTarget",
    "OutboundAuthType",
    "TargetRegistry",
    "TargetType",
    "ToolDiscovery",
]
