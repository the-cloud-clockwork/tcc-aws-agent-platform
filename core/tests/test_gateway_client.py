"""Unit tests for AgentCore Gateway client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from agent_core.gateway.client import (
    GatewayClient,
    GatewayPolicyDeniedError,
)


class TestGatewayClient:
    """Tests for GatewayClient."""

    def test_init_defaults(self):
        client = GatewayClient()
        assert client.gateway_url == "http://localhost:9000"
        assert client.timeout == 30.0

    def test_init_custom_url(self):
        client = GatewayClient(gateway_url="https://gateway.example.com")
        assert client.gateway_url == "https://gateway.example.com"

    @patch("httpx.Client.post")
    def test_invoke_tool_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "output": {"target": "AAPL", "data": [100, 105, 98, 103, 1000000]},
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = GatewayClient(gateway_url="http://test:9000")
        client._http_client = MagicMock()
        client._http_client.post = mock_post

        result = client.invoke_tool(
            "data-mcp::get_data",
            {"target": "AAPL", "date": "2026-03-15"},
        )

        assert result["target"] == "AAPL"

    @patch("httpx.Client.post")
    def test_invoke_tool_policy_denied(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden",
            request=MagicMock(),
            response=mock_response,
        )
        mock_post.return_value = mock_response

        client = GatewayClient(gateway_url="http://test:9000")
        client._http_client = MagicMock()
        client._http_client.post = mock_post

        with pytest.raises(GatewayPolicyDeniedError):
            client.invoke_tool(
                "executor-mcp::execute_action",
                {"target": "AAPL"},
                agent_id="test-agent",
            )

    @patch("httpx.Client.get")
    def test_list_tools(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tools": [
                {"name": "get_data", "target": "data-mcp"},
                {"name": "get_status", "target": "executor-mcp"},
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        client = GatewayClient(gateway_url="http://test:9000")
        client._http_client = MagicMock()
        client._http_client.get = mock_get

        tools = client.list_tools()
        assert len(tools) == 2

    @patch("httpx.Client.post")
    def test_search_tools(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tools": [
                {"name": "get_data", "relevance_score": 0.95},
            ],
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = GatewayClient(gateway_url="http://test:9000")
        client._http_client = MagicMock()
        client._http_client.post = mock_post

        tools = client.search_tools("historical price data")
        assert len(tools) == 1

    def test_context_manager(self):
        with GatewayClient(gateway_url="http://test:9000") as client:
            assert client.gateway_url == "http://test:9000"
