"""Gateway configuration schema for agent blueprints."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class GatewayAuthType(str, Enum):
    """Inbound auth type for Gateway connections."""

    AWS_IAM = "aws_iam"
    CUSTOM_JWT = "custom_jwt"
    NONE = "none"


class GatewayConfig(BaseModel):
    """Gateway configuration for an agent blueprint.

    All tool access goes through the AgentCore Gateway.  The Gateway
    auto-generates MCP interfaces from Lambda functions, REST APIs,
    OpenAPI specs, and MCP servers.  No direct MCP connections.
    """

    model_config = ConfigDict(frozen=True)

    url: str | None = Field(
        default=None,
        description=(
            "Gateway URL.  Falls back to AGENTCORE_GATEWAY_URL env var when None."
        ),
    )
    auth_type: GatewayAuthType = Field(
        default=GatewayAuthType.AWS_IAM,
        description="Inbound auth: AWS_IAM (SigV4) or CUSTOM_JWT (user token passthrough).",
    )
    jwt_env_var: str | None = Field(
        default=None,
        description="Env var name holding the JWT for CUSTOM_JWT auth.",
    )
    region: str = Field(
        default="eu-west-1",
        description="AWS region for SigV4 signing.",
    )
    service_name: str = Field(
        default="bedrock-agentcore",
        description="AWS service name for SigV4 signing.",
    )
