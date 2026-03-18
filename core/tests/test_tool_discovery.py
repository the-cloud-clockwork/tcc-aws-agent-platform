"""Unit tests for semantic tool discovery."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agent_core.gateway.tool_discovery import ToolDiscovery, DiscoveredTool


class TestToolDiscovery:
    """Tests for ToolDiscovery."""

    def test_find_tools(self):
        mock_gateway = MagicMock()
        mock_gateway.search_tools.return_value = [
            {
                "fqn": "data-mcp::get_data",
                "target": "data-mcp",
                "name": "get_data",
                "description": "Get time-series data",
                "input_schema": {},
                "relevance_score": 0.9,
            },
            {
                "fqn": "data-mcp::get_volume",
                "target": "data-mcp",
                "name": "get_volume",
                "description": "Get volume profile",
                "input_schema": {},
                "relevance_score": 0.2,
            },
        ]

        discovery = ToolDiscovery(mock_gateway)
        tools = discovery.find_tools("price data", min_relevance=0.3)

        assert len(tools) == 1
        assert tools[0].fqn == "data-mcp::get_data"

    def test_find_tools_for_task(self):
        mock_gateway = MagicMock()
        mock_gateway.search_tools.return_value = [
            {
                "fqn": "my-mcp::do_thing",
                "target": "my-mcp",
                "name": "do_thing",
                "description": "Do something",
                "input_schema": {},
                "relevance_score": 0.8,
            },
        ]

        discovery = ToolDiscovery(mock_gateway)
        tools = discovery.find_tools_for_task(
            "analyze data",
            agent_id="my-agent",
        )

        # Generic _agent_can_use always returns True
        assert len(tools) == 1
        assert tools[0].fqn == "my-mcp::do_thing"

    def test_agent_can_use_always_true(self):
        """Generic _agent_can_use always returns True (Cedar handles enforcement)."""
        assert ToolDiscovery._agent_can_use("any-agent", "any-mcp::any_tool")
        assert ToolDiscovery._agent_can_use("test", "executor-mcp::place_order")
