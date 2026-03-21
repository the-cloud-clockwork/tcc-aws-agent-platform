"""Tests for agent_core.gateway.client — GatewayClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestGatewayClient:
    """Test GatewayClient construction, auth modes, and from_config."""

    @patch.dict("os.environ", {"AWS_REGION": "us-west-2"})
    @patch("agent_core.gateway.client.GatewayClient._init_sdk_client")
    def test_construction_iam_auth(self, mock_init: MagicMock) -> None:
        from agent_core.gateway.client import GatewayClient

        client = GatewayClient(
            gateway_url="https://gw.example.com",
            auth_type="aws_iam",
            region="us-west-2",
        )
        assert client is not None

    @patch("agent_core.gateway.client.GatewayClient._init_sdk_client")
    def test_construction_no_auth(self, mock_init: MagicMock) -> None:
        from agent_core.gateway.client import GatewayClient

        client = GatewayClient(
            gateway_url="http://localhost:8080",
            auth_type="none",
            region="us-west-2",
        )
        assert client is not None

    @patch("agent_core.gateway.client.GatewayClient._init_sdk_client")
    def test_from_config(self, mock_init: MagicMock) -> None:
        from agent_core.schemas.gateway_config import GatewayAuthType, GatewayConfig

        config = GatewayConfig(
            url="https://gw.example.com",
            auth_type=GatewayAuthType.AWS_IAM,
            region="eu-west-1",
        )

        from agent_core.gateway.client import GatewayClient

        client = GatewayClient.from_config(config)
        assert client is not None

    def test_missing_region_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with patch("agent_core.gateway.client.GatewayClient._init_sdk_client"):
                from agent_core.gateway.client import GatewayClient

                with pytest.raises(Exception):
                    GatewayClient(gateway_url="https://gw.example.com")

    @patch.dict("os.environ", {"JWT_TOKEN": "test-jwt-123"})
    @patch("agent_core.gateway.client.GatewayClient._init_sdk_client")
    def test_jwt_auth(self, mock_init: MagicMock) -> None:
        from agent_core.gateway.client import GatewayClient

        client = GatewayClient(
            gateway_url="https://gw.example.com",
            auth_type="custom_jwt",
            jwt_env_var="JWT_TOKEN",
            region="us-west-2",
        )
        assert client is not None
