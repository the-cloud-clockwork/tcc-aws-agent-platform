"""Tests for concrete IdentityProvider subclasses (Cognito, Okta, Entra)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_core.identity.cache import CredentialCache
from agent_core.identity.cognito import CognitoProvider
from agent_core.identity.entra import EntraProvider
from agent_core.identity.okta import OktaProvider
from agent_core.identity.providers import Credential, CredentialError


_MOCK_TOKEN = {
    "token_type": "bearer",
    "access_token": "tok-abc",
    "expires_at": "2099-01-01T00:00:00Z",
    "scopes": ["read"],
}


class TestCognitoProvider:
    @patch("agent_core.identity.providers.AgentCoreIdentityClient")
    def test_get_credential(self, mock_client_cls: MagicMock) -> None:
        mock_client_cls.return_value.get_credential.return_value = _MOCK_TOKEN
        provider = CognitoProvider(credential_id="cog-cred")
        cred = provider.get_credential()
        assert isinstance(cred, Credential)
        assert cred.access_token == "tok-abc"
        assert cred.provider == "cognito"

    @patch("agent_core.identity.providers.AgentCoreIdentityClient")
    def test_get_credential_with_cache(self, mock_client_cls: MagicMock) -> None:
        mock_client_cls.return_value.get_credential.return_value = _MOCK_TOKEN
        cache = CredentialCache()
        provider = CognitoProvider(credential_id="cog-cred", cache=cache)

        cred1 = provider.get_credential()
        cred2 = provider.get_credential()  # Should hit cache

        assert cred1.access_token == cred2.access_token
        # Only one SDK call — second was cached
        mock_client_cls.return_value.get_credential.assert_called_once()

    @patch("agent_core.identity.providers.AgentCoreIdentityClient")
    def test_refresh_credential_invalidates_cache(self, mock_client_cls: MagicMock) -> None:
        mock_client_cls.return_value.get_credential.return_value = _MOCK_TOKEN
        cache = CredentialCache()
        provider = CognitoProvider(credential_id="cog-cred", cache=cache)

        provider.get_credential()
        provider.refresh_credential()

        # Two SDK calls: initial get + refresh
        assert mock_client_cls.return_value.get_credential.call_count == 2

    @patch("agent_core.identity.providers.AgentCoreIdentityClient")
    def test_sdk_error_raises_credential_error(self, mock_client_cls: MagicMock) -> None:
        mock_client_cls.return_value.get_credential.side_effect = RuntimeError("boom")
        provider = CognitoProvider()
        with pytest.raises(CredentialError):
            provider.get_credential()


class TestOktaProvider:
    @patch("agent_core.identity.providers.AgentCoreIdentityClient")
    def test_get_credential(self, mock_client_cls: MagicMock) -> None:
        mock_client_cls.return_value.get_credential.return_value = _MOCK_TOKEN
        provider = OktaProvider(credential_id="okta-cred")
        cred = provider.get_credential()
        assert cred.provider == "okta"
        assert cred.access_token == "tok-abc"


class TestEntraProvider:
    @patch("agent_core.identity.providers.AgentCoreIdentityClient")
    def test_get_credential(self, mock_client_cls: MagicMock) -> None:
        mock_client_cls.return_value.get_credential.return_value = _MOCK_TOKEN
        provider = EntraProvider(credential_id="entra-cred")
        cred = provider.get_credential()
        assert cred.provider == "entra"
        assert cred.access_token == "tok-abc"


class TestProviderRegistry:
    def test_register_and_get(self) -> None:
        from agent_core.identity.providers import ProviderRegistry

        registry = ProviderRegistry()
        registry.register("cognito", CognitoProvider)
        provider = registry.get("cognito")
        assert isinstance(provider, CognitoProvider)

    def test_get_unknown_raises(self) -> None:
        from agent_core.identity.providers import ProviderRegistry

        registry = ProviderRegistry()
        with pytest.raises(ValueError, match="Unknown provider"):
            registry.get("missing")
