"""Tests for IdentityWiring."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from agent_core.identity.wiring import IdentityWiring
from agent_core.schemas.identity_config import (
    AuthFlow,
    CredentialConfig,
    CredentialType,
)


def _api_key_cred(name: str = "ext-api") -> CredentialConfig:
    return CredentialConfig(name=name, type=CredentialType.API_KEY, provider="ext-provider")


def _oauth2_cred(name: str = "google-cal", auth_flow: AuthFlow = AuthFlow.USER_FEDERATION) -> CredentialConfig:
    return CredentialConfig(
        name=name,
        type=CredentialType.OAUTH2,
        provider="google-provider",
        scopes=["calendar"],
        auth_flow=auth_flow,
        callback_url_env="CALLBACK_URL",
    )


class TestIdentityWiring:
    def test_get_credential_map(self) -> None:
        wiring = IdentityWiring(credentials=[_api_key_cred(), _oauth2_cred()])
        cred_map = wiring.get_credential_map()
        assert "ext-api" in cred_map
        assert "google-cal" in cred_map

    @patch("agent_core.identity.wiring.requires_api_key")
    def test_get_api_key_decorator(self, mock_decorator: object) -> None:
        wiring = IdentityWiring(credentials=[_api_key_cred()])
        wiring.get_api_key_decorator("ext-api")
        # Decorator factory was called with correct provider

    @patch("agent_core.identity.wiring.requires_access_token")
    def test_get_access_token_decorator(self, mock_decorator: object) -> None:
        wiring = IdentityWiring(credentials=[_oauth2_cred()])
        wiring.get_access_token_decorator("google-cal")

    def test_unknown_credential_raises(self) -> None:
        wiring = IdentityWiring(credentials=[_api_key_cred()])
        with pytest.raises(ValueError, match="not declared"):
            wiring.get_api_key_decorator("nonexistent")

    def test_wrong_type_raises(self) -> None:
        wiring = IdentityWiring(credentials=[_api_key_cred()])
        with pytest.raises(ValueError, match="type 'api_key'"):
            wiring.get_access_token_decorator("ext-api")

    def test_default_on_auth_url_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING):
            IdentityWiring.default_on_auth_url("https://example.com/auth")
        assert "https://example.com/auth" in caplog.text
