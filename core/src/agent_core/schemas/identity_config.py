"""Pydantic models for the ``identity:`` block in agent blueprints."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AuthorizerType(str, Enum):
    """Inbound authorizer type for validating callers."""

    CUSTOM_JWT = "custom_jwt"
    AWS_IAM = "aws_iam"


class AuthorizerConfig(BaseModel):
    """Inbound JWT/IAM authorizer configuration.

    Declares how the AgentCore Runtime validates incoming requests
    before they reach the agent's ``@app.entrypoint``.
    """

    model_config = ConfigDict(frozen=True)

    type: AuthorizerType = Field(
        default=AuthorizerType.CUSTOM_JWT,
        description="Authorizer type for inbound request validation.",
    )
    discovery_url: str | None = Field(
        default=None,
        description="OIDC discovery URL (e.g. Cognito .well-known/openid-configuration).",
    )
    allowed_clients: list[str] = Field(
        default_factory=list,
        description="Allowed OAuth2 client IDs (audience values).",
    )


class AuthFlow(str, Enum):
    """Outbound OAuth2 auth flow type."""

    USER_FEDERATION = "USER_FEDERATION"
    M2M = "M2M"


class CredentialType(str, Enum):
    """Outbound credential provider type."""

    API_KEY = "api_key"
    OAUTH2 = "oauth2"


class CredentialConfig(BaseModel):
    """Single outbound credential provider declaration.

    Each entry maps to a credential provider registered in
    AgentCore Identity. The platform resolves credentials at
    runtime via ``@requires_api_key`` or ``@requires_access_token``.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(
        ...,
        description="Credential provider name (referenced by decorators).",
    )
    type: CredentialType = Field(
        ...,
        description="api_key or oauth2.",
    )
    provider: str = Field(
        ...,
        description="Provider name registered in AgentCore Identity.",
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="OAuth2 scopes (for oauth2 type).",
    )
    auth_flow: AuthFlow | None = Field(
        default=None,
        description="Auth flow: USER_FEDERATION (3LO) or M2M. Required for oauth2 type.",
    )
    callback_url_env: str | None = Field(
        default=None,
        description="Env var name holding the OAuth2 callback URL (3LO only).",
    )


class IdentityConfig(BaseModel):
    """Identity configuration block for an agent blueprint.

    Declares inbound authorizer (who can call this agent) and
    outbound credential providers (what external services the
    agent can authenticate to).
    """

    model_config = ConfigDict(frozen=True)

    authorizer: AuthorizerConfig | None = Field(
        default=None,
        description="Inbound JWT/IAM authorizer configuration.",
    )
    credentials: list[CredentialConfig] = Field(
        default_factory=list,
        description="Outbound credential provider declarations.",
    )
