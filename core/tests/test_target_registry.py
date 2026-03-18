"""Unit tests for Gateway target registry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_core.gateway.target_registry import (
    GatewayTarget,
    TargetType,
    AuthType,
    TargetRegistry,
)


class TestGatewayTarget:
    """Tests for GatewayTarget dataclass."""

    def test_mcp_server_target(self):
        target = GatewayTarget(
            name="test-mcp",
            target_type=TargetType.MCP_SERVER,
            endpoint="test-mcp.local:8000",
        )
        assert target.auth_type == AuthType.NONE
        assert target.max_tools == 10000

    def test_openapi_target(self):
        target = GatewayTarget(
            name="my-api",
            target_type=TargetType.OPENAPI,
            endpoint="https://api.example.com",
            auth_type=AuthType.API_KEY,
            auth_config={"header_name": "Authorization", "key_ref": "MY_API_KEY"},
        )
        assert target.target_type == TargetType.OPENAPI
        assert target.auth_config["key_ref"] == "MY_API_KEY"


class TestTargetRegistry:
    """Tests for TargetRegistry operations."""

    @patch("httpx.Client.post")
    def test_register_target(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"tool_count": 15}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        registry = TargetRegistry(gateway_url="http://test:9000")
        registry._client = MagicMock()
        registry._client.post = mock_post

        target = GatewayTarget(
            name="test-mcp",
            target_type=TargetType.MCP_SERVER,
            endpoint="test.local:8000",
        )
        result = registry.register_target(target)
        assert result["tool_count"] == 15

    @patch("httpx.Client.post")
    def test_synchronize_all(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"tool_count": 10}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        registry = TargetRegistry(gateway_url="http://test:9000")
        registry._client = MagicMock()
        registry._client.post = mock_post

        targets = [
            GatewayTarget(name="a", target_type=TargetType.MCP_SERVER, endpoint="a:8000"),
            GatewayTarget(name="b", target_type=TargetType.MCP_SERVER, endpoint="b:8000"),
        ]
        result = registry.synchronize_all(targets)

        assert result["total_tools"] == 20
        assert result["targets"]["a"]["status"] == "registered"
