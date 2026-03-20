"""Tests for BaseMCPServer — transport selection, tool dispatch, error wrapping."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_core.mcp.base_server import BaseMCPServer
from mcp.types import Tool


@pytest.fixture
def mcp():
    return BaseMCPServer("test-mcp", default_port=9999)


class TestToolRegistration:
    def test_tool_decorator_registers_tool(self, mcp):
        tool_def = Tool(
            name="greet",
            description="Say hello",
            inputSchema={"type": "object", "properties": {"name": {"type": "string"}}},
        )

        @mcp.tool(tool_def)
        async def greet(arguments):
            return {"message": f"Hello {arguments['name']}"}

        assert len(mcp._tools) == 1
        assert mcp._tools[0].name == "greet"
        assert "greet" in mcp._handlers

    def test_multiple_tools(self, mcp):
        for i in range(3):
            tool_def = Tool(name=f"tool_{i}", description=f"Tool {i}", inputSchema={"type": "object"})

            @mcp.tool(tool_def)
            async def handler(arguments, _i=i):
                return {"i": _i}

        assert len(mcp._tools) == 3


class TestListTools:
    async def test_list_tools_returns_registered(self, mcp):
        tool_def = Tool(name="ping", description="Ping", inputSchema={"type": "object"})

        @mcp.tool(tool_def)
        async def ping(arguments):
            return {"pong": True}

        result = await mcp._list_tools()
        assert len(result) == 1
        assert result[0].name == "ping"


class TestCallTool:
    async def test_successful_call(self, mcp):
        tool_def = Tool(name="add", description="Add numbers", inputSchema={"type": "object"})

        @mcp.tool(tool_def)
        async def add(arguments):
            return {"result": arguments["a"] + arguments["b"]}

        result = await mcp._call_tool("add", {"a": 1, "b": 2})
        assert len(result) == 1
        data = json.loads(result[0].text)
        assert data["result"] == 3

    async def test_error_wrapping(self, mcp):
        tool_def = Tool(name="fail", description="Always fails", inputSchema={"type": "object"})

        @mcp.tool(tool_def)
        async def fail(arguments):
            raise ValueError("deliberate error")

        result = await mcp._call_tool("fail", {})
        data = json.loads(result[0].text)
        assert data["error"] == "ValueError"
        assert "deliberate error" in data["message"]
        assert "traceback" in data

    async def test_unknown_tool(self, mcp):
        result = await mcp._call_tool("nonexistent", {})
        data = json.loads(result[0].text)
        assert data["error"] == "ValueError"
        assert "Unknown tool" in data["message"]


class TestTransportSelection:
    @patch.dict("os.environ", {"MCP_TRANSPORT": "stdio"})
    @patch.object(BaseMCPServer, "_run_stdio", new_callable=lambda: lambda self: None)
    def test_stdio_selected(self, mock_run, mcp):
        with patch("asyncio.run") as mock_asyncio:
            mock_asyncio.side_effect = lambda coro: None
            mcp.run()

    @patch.dict("os.environ", {"MCP_TRANSPORT": "http"})
    @patch.object(BaseMCPServer, "_run_http")
    def test_http_selected(self, mock_run, mcp):
        mcp.run()
        mock_run.assert_called_once()

    @patch.dict("os.environ", {"MCP_TRANSPORT": "sse"})
    @patch.object(BaseMCPServer, "_run_sse")
    def test_sse_selected(self, mock_run, mcp):
        mcp.run()
        mock_run.assert_called_once()

    @patch.dict("os.environ", {"MCP_TRANSPORT": "invalid"})
    def test_invalid_transport_exits(self, mcp):
        with pytest.raises(SystemExit):
            mcp.run()


class TestBackgroundTasks:
    def test_add_background_task(self, mcp):
        async def poller():
            pass

        mcp.add_background_task(poller)
        assert len(mcp._background_tasks) == 1

    @patch.dict("os.environ", {"MCP_TRANSPORT": "stdio"})
    def test_stdio_with_background_uses_background_runner(self, mcp):
        async def poller():
            pass

        mcp.add_background_task(poller)

        with patch("asyncio.run") as mock_asyncio:
            mock_asyncio.side_effect = lambda coro: None
            mcp.run()
