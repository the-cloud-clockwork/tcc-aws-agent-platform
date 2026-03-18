"""Tests for MCP server module — tool registry and dispatch."""
import json
import pytest
from unittest.mock import AsyncMock, patch

from mcp_artifacts.server import TOOLS, handle_list_tools, handle_call_tool


class TestToolRegistry:
    def test_tools_list_not_empty(self):
        assert len(TOOLS) == 4

    def test_tool_names(self):
        names = {t.name for t in TOOLS}
        assert names == {"create_artifact", "get_artifact", "poll_artifact", "list_artifacts"}

    def test_all_tools_have_schemas(self):
        for tool in TOOLS:
            assert tool.inputSchema is not None
            assert tool.inputSchema["type"] == "object"


class TestHandleListTools:
    @pytest.mark.asyncio
    async def test_returns_all_tools(self):
        result = await handle_list_tools()
        assert len(result) == 4


class TestHandleCallTool:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        result = await handle_call_tool("nonexistent_tool", {})
        assert len(result) == 1
        data = json.loads(result[0].text)
        assert "error" in data
        assert "Unknown tool" in data["error"]

    @pytest.mark.asyncio
    async def test_dispatches_to_handler(self):
        mock_result = {"artifact_id": "abc-123", "status": "ready"}
        with patch("mcp_artifacts.server.get_artifact", new_callable=AsyncMock, return_value=mock_result):
            result = await handle_call_tool("get_artifact", {"artifact_id": "abc-123"})

        data = json.loads(result[0].text)
        assert data["artifact_id"] == "abc-123"

    @pytest.mark.asyncio
    async def test_handler_exception_returns_error(self):
        with patch("mcp_artifacts.server.create_artifact", new_callable=AsyncMock, side_effect=ValueError("bad input")):
            result = await handle_call_tool("create_artifact", {"type": "chart", "content": "x"})

        data = json.loads(result[0].text)
        assert "error" in data
        assert "bad input" in data["error"]
