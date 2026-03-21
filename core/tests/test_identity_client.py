"""Tests for IdentityClient wrapper."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_core.identity.providers import CredentialError


class TestIdentityClient:
    @patch("agent_core.identity.client.SdkIdentityClient")
    def test_create_api_key_provider(self, mock_sdk_cls: MagicMock) -> None:
        mock_sdk = MagicMock()
        mock_sdk.create_api_key_credential_provider.return_value = {"name": "my-key"}
        mock_sdk_cls.return_value = mock_sdk

        from agent_core.identity.client import IdentityClient

        client = IdentityClient(region="us-east-1")
        result = client.create_api_key_provider("my-key", "my-secret")
        assert result["name"] == "my-key"
        mock_sdk.create_api_key_credential_provider.assert_called_once()

    @patch("agent_core.identity.client.SdkIdentityClient")
    def test_create_oauth2_provider(self, mock_sdk_cls: MagicMock) -> None:
        mock_sdk = MagicMock()
        mock_sdk.create_oauth2_credential_provider.return_value = {"name": "oauth"}
        mock_sdk_cls.return_value = mock_sdk

        from agent_core.identity.client import IdentityClient

        client = IdentityClient(region="us-east-1")
        result = client.create_oauth2_provider(
            "oauth",
            client_id="cid",
            client_secret="csec",
            authorization_url="https://auth.example.com/authorize",
            token_url="https://auth.example.com/token",
            scopes=["openid"],
        )
        assert result["name"] == "oauth"

    @patch("agent_core.identity.client.SdkIdentityClient")
    def test_get_provider(self, mock_sdk_cls: MagicMock) -> None:
        mock_sdk = MagicMock()
        mock_sdk.get_credential_provider.return_value = {"name": "p1", "type": "api_key"}
        mock_sdk_cls.return_value = mock_sdk

        from agent_core.identity.client import IdentityClient

        client = IdentityClient()
        result = client.get_provider("p1")
        assert result["type"] == "api_key"

    @patch("agent_core.identity.client.SdkIdentityClient")
    def test_list_providers(self, mock_sdk_cls: MagicMock) -> None:
        mock_sdk = MagicMock()
        mock_sdk.list_credential_providers.return_value = [{"name": "a"}, {"name": "b"}]
        mock_sdk_cls.return_value = mock_sdk

        from agent_core.identity.client import IdentityClient

        client = IdentityClient()
        result = client.list_providers()
        assert len(result) == 2

    @patch("agent_core.identity.client.SdkIdentityClient")
    def test_delete_provider(self, mock_sdk_cls: MagicMock) -> None:
        mock_sdk = MagicMock()
        mock_sdk_cls.return_value = mock_sdk

        from agent_core.identity.client import IdentityClient

        client = IdentityClient()
        client.delete_provider("p1")
        mock_sdk.delete_credential_provider.assert_called_once_with("p1")

    @patch("agent_core.identity.client.SdkIdentityClient")
    def test_sdk_error_raises_credential_error(self, mock_sdk_cls: MagicMock) -> None:
        mock_sdk = MagicMock()
        mock_sdk.get_credential_provider.side_effect = RuntimeError("boom")
        mock_sdk_cls.return_value = mock_sdk

        from agent_core.identity.client import IdentityClient

        client = IdentityClient()
        with pytest.raises(CredentialError, match="boom"):
            client.get_provider("missing")

    @patch("agent_core.identity.client.SdkIdentityClient", side_effect=ImportError("no SDK"))
    def test_init_failure_raises_credential_error(self, mock_sdk_cls: MagicMock) -> None:
        from agent_core.identity.client import IdentityClient

        with pytest.raises(CredentialError, match="Failed to initialise"):
            IdentityClient()
