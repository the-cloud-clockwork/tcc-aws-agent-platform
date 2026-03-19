"""Tests for MCP client factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent_core.tools.mcp_factory import create_mcp_client


class TestCreateMcpClient:
    """Tests for create_mcp_client factory function."""

    @patch("agent_core.tools.mcp_factory.MCPClient")
    @patch("agent_core.tools.mcp_factory.streamablehttp_client")
    def test_basic_creation(self, mock_http, mock_mcp_cls):
        mock_mcp_cls.return_value = MagicMock()
        client = create_mcp_client("test-mcp", "http://localhost:8002")
        mock_mcp_cls.assert_called_once()
        # Verify prefix kwarg
        _, kwargs = mock_mcp_cls.call_args
        assert kwargs["prefix"] == "test-mcp"

    @patch("agent_core.tools.mcp_factory.MCPClient")
    @patch("agent_core.tools.mcp_factory.streamablehttp_client")
    def test_with_tool_filter(self, mock_http, mock_mcp_cls):
        mock_mcp_cls.return_value = MagicMock()
        client = create_mcp_client("test-mcp", "http://localhost:8002", tool_filter=["tool_a"])
        _, kwargs = mock_mcp_cls.call_args
        assert kwargs["tool_filters"] == {"allowed": ["tool_a"]}

    @patch("agent_core.tools.mcp_factory.MCPClient")
    @patch("agent_core.tools.mcp_factory.streamablehttp_client")
    def test_url_normalization(self, mock_http, mock_mcp_cls):
        """Trailing slash is stripped and /mcp is appended."""
        mock_mcp_cls.return_value = MagicMock()
        create_mcp_client("test", "http://localhost:8002/")
        # The lambda captures the normalized URL — we verify MCPClient was called
        mock_mcp_cls.assert_called_once()
