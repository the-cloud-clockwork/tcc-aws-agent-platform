"""Tests for identity blueprint schema (Pydantic models)."""
from __future__ import annotations

import pytest
import yaml

from agent_core.blueprints.agent import AgentBlueprint
from agent_core.schemas.identity_config import (
    AuthFlow,
    AuthorizerConfig,
    AuthorizerType,
    CredentialConfig,
    CredentialType,
    IdentityConfig,
)


class TestIdentityConfig:
    def test_default_identity_config(self) -> None:
        cfg = IdentityConfig()
        assert cfg.authorizer is None
        assert cfg.credentials == []

    def test_authorizer_custom_jwt(self) -> None:
        auth = AuthorizerConfig(
            type=AuthorizerType.CUSTOM_JWT,
            discovery_url="https://cognito.example.com/.well-known/openid-configuration",
            allowed_clients=["client-a", "client-b"],
        )
        assert auth.type == AuthorizerType.CUSTOM_JWT
        assert "cognito" in auth.discovery_url
        assert len(auth.allowed_clients) == 2

    def test_authorizer_aws_iam(self) -> None:
        auth = AuthorizerConfig(type=AuthorizerType.AWS_IAM)
        assert auth.type == AuthorizerType.AWS_IAM
        assert auth.discovery_url is None

    def test_credential_api_key(self) -> None:
        cred = CredentialConfig(
            name="external-api",
            type=CredentialType.API_KEY,
            provider="ext-apikey-provider",
        )
        assert cred.name == "external-api"
        assert cred.type == CredentialType.API_KEY
        assert cred.scopes == []
        assert cred.auth_flow is None

    def test_credential_oauth2_3lo(self) -> None:
        cred = CredentialConfig(
            name="google-cal",
            type=CredentialType.OAUTH2,
            provider="google-cal-provider",
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
            auth_flow=AuthFlow.USER_FEDERATION,
            callback_url_env="CALLBACK_URL",
        )
        assert cred.type == CredentialType.OAUTH2
        assert cred.auth_flow == AuthFlow.USER_FEDERATION
        assert len(cred.scopes) == 1
        assert cred.callback_url_env == "CALLBACK_URL"

    def test_credential_m2m(self) -> None:
        cred = CredentialConfig(
            name="agent-m2m",
            type=CredentialType.OAUTH2,
            provider="monitor-agent-provider",
            auth_flow=AuthFlow.M2M,
        )
        assert cred.auth_flow == AuthFlow.M2M
        assert cred.scopes == []

    def test_full_identity_config(self) -> None:
        cfg = IdentityConfig(
            authorizer=AuthorizerConfig(
                type=AuthorizerType.CUSTOM_JWT,
                discovery_url="https://example.com",
                allowed_clients=["c1"],
            ),
            credentials=[
                CredentialConfig(name="a", type=CredentialType.API_KEY, provider="p1"),
                CredentialConfig(
                    name="b",
                    type=CredentialType.OAUTH2,
                    provider="p2",
                    auth_flow=AuthFlow.M2M,
                ),
            ],
        )
        assert cfg.authorizer is not None
        assert len(cfg.credentials) == 2

    def test_credential_missing_required_fields(self) -> None:
        with pytest.raises(Exception):
            CredentialConfig(name="x")  # type: ignore[call-arg]


class TestIdentityInBlueprint:
    def test_blueprint_default_identity(self) -> None:
        bp = AgentBlueprint(
            id="test",
            version="1",
            name="Test",
            model={"provider": "bedrock", "model_id": "x"},
            prompt_ref="p",
        )
        assert bp.identity.authorizer is None
        assert bp.identity.credentials == []

    def test_blueprint_with_identity(self) -> None:
        bp = AgentBlueprint(
            id="test",
            version="1",
            name="Test",
            model={"provider": "bedrock", "model_id": "x"},
            prompt_ref="p",
            identity={
                "authorizer": {
                    "type": "custom_jwt",
                    "discovery_url": "https://example.com",
                },
                "credentials": [
                    {"name": "api", "type": "api_key", "provider": "my-provider"},
                ],
            },
        )
        assert bp.identity.authorizer.type == AuthorizerType.CUSTOM_JWT
        assert len(bp.identity.credentials) == 1

    def test_blueprint_yaml_roundtrip(self) -> None:
        yaml_str = """
id: test-agent
version: "1.0"
name: Test Agent
model:
  provider: bedrock
  model_id: eu.anthropic.claude-sonnet-4-6
prompt_ref: test_prompt
identity:
  authorizer:
    type: custom_jwt
    discovery_url: https://cognito.example.com
    allowed_clients:
      - client-1
  credentials:
    - name: ext-api
      type: api_key
      provider: ext-apikey-provider
    - name: google-cal
      type: oauth2
      provider: google-cal-provider
      scopes:
        - https://www.googleapis.com/auth/calendar.readonly
      auth_flow: USER_FEDERATION
      callback_url_env: CALLBACK_URL
"""
        data = yaml.safe_load(yaml_str)
        bp = AgentBlueprint(**data)
        assert bp.identity.authorizer is not None
        assert bp.identity.authorizer.type == AuthorizerType.CUSTOM_JWT
        assert len(bp.identity.credentials) == 2
        assert bp.identity.credentials[0].type == CredentialType.API_KEY
        assert bp.identity.credentials[1].auth_flow == AuthFlow.USER_FEDERATION
