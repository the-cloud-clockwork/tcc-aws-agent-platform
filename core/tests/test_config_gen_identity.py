"""Tests for identity wiring in config_gen.py."""
from __future__ import annotations

import yaml

from agent_core.blueprints.agent import AgentBlueprint
from agent_core.runtime.config_gen import generate_agentcore_config
from agent_core.schemas.identity_config import (
    AuthFlow,
    AuthorizerConfig,
    AuthorizerType,
    CredentialConfig,
    CredentialType,
    IdentityConfig,
)


def _make_blueprint(**identity_kwargs: object) -> AgentBlueprint:
    return AgentBlueprint(
        id="test-agent",
        version="1",
        name="Test",
        model={"provider": "bedrock", "model_id": "x", "temperature": 0.5, "max_tokens": 1024},
        prompt_ref="p",
        identity=IdentityConfig(**identity_kwargs),
    )


class TestConfigGenIdentity:
    def test_default_identity_produces_empty_providers(self) -> None:
        bp = _make_blueprint()
        config_yaml = generate_agentcore_config(bp)
        config = yaml.safe_load(config_yaml)
        identity = config["agents"]["test-agent"]["identity"]
        assert identity["credential_providers"] == []
        assert "authorizer_configuration" not in identity

    def test_custom_jwt_authorizer(self) -> None:
        bp = _make_blueprint(
            authorizer=AuthorizerConfig(
                type=AuthorizerType.CUSTOM_JWT,
                discovery_url="https://cognito.example.com/.well-known/openid-configuration",
                allowed_clients=["client-1", "client-2"],
            )
        )
        config_yaml = generate_agentcore_config(bp)
        config = yaml.safe_load(config_yaml)
        identity = config["agents"]["test-agent"]["identity"]
        auth = identity["authorizer_configuration"]["customJWTAuthorizer"]
        assert auth["discoveryUrl"] == "https://cognito.example.com/.well-known/openid-configuration"
        assert auth["allowedClients"] == ["client-1", "client-2"]

    def test_aws_iam_authorizer_no_config(self) -> None:
        bp = _make_blueprint(
            authorizer=AuthorizerConfig(type=AuthorizerType.AWS_IAM)
        )
        config_yaml = generate_agentcore_config(bp)
        config = yaml.safe_load(config_yaml)
        identity = config["agents"]["test-agent"]["identity"]
        assert "authorizer_configuration" not in identity

    def test_api_key_credential(self) -> None:
        bp = _make_blueprint(
            credentials=[
                CredentialConfig(
                    name="ext-api",
                    type=CredentialType.API_KEY,
                    provider="ext-apikey-provider",
                )
            ]
        )
        config_yaml = generate_agentcore_config(bp)
        config = yaml.safe_load(config_yaml)
        providers = config["agents"]["test-agent"]["identity"]["credential_providers"]
        assert len(providers) == 1
        assert providers[0]["name"] == "ext-apikey-provider"
        assert providers[0]["type"] == "api_key"
        assert "auth_flow" not in providers[0]

    def test_oauth2_credential_with_scopes(self) -> None:
        bp = _make_blueprint(
            credentials=[
                CredentialConfig(
                    name="google-cal",
                    type=CredentialType.OAUTH2,
                    provider="google-cal-provider",
                    scopes=["calendar.readonly"],
                    auth_flow=AuthFlow.USER_FEDERATION,
                )
            ]
        )
        config_yaml = generate_agentcore_config(bp)
        config = yaml.safe_load(config_yaml)
        providers = config["agents"]["test-agent"]["identity"]["credential_providers"]
        assert providers[0]["type"] == "oauth2"
        assert providers[0]["scopes"] == ["calendar.readonly"]
        assert providers[0]["auth_flow"] == "USER_FEDERATION"

    def test_multiple_credentials(self) -> None:
        bp = _make_blueprint(
            credentials=[
                CredentialConfig(name="a", type=CredentialType.API_KEY, provider="p1"),
                CredentialConfig(
                    name="b",
                    type=CredentialType.OAUTH2,
                    provider="p2",
                    auth_flow=AuthFlow.M2M,
                ),
            ]
        )
        config_yaml = generate_agentcore_config(bp)
        config = yaml.safe_load(config_yaml)
        providers = config["agents"]["test-agent"]["identity"]["credential_providers"]
        assert len(providers) == 2
