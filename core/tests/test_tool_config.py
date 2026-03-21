"""Tests for ToolConfig schemas — MCP and builtin tool declarations."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_core.blueprints.agent import AgentBlueprint
from agent_core.schemas.tool_config import (
    BuiltinToolConfig,
    BuiltinToolType,
    McpToolConfig,
    ToolConfig,
    ToolDeclaration,
)


class TestMcpToolConfig:
    def test_valid(self):
        cfg = McpToolConfig(mcp="data-mcp", tools=["get_data", "query"])
        assert cfg.mcp == "data-mcp"
        assert cfg.tools == ["get_data", "query"]

    def test_tools_required(self):
        with pytest.raises(ValidationError):
            McpToolConfig(mcp="data-mcp", tools=[])

    def test_mcp_required(self):
        with pytest.raises(ValidationError):
            McpToolConfig(tools=["get_data"])

    def test_frozen(self):
        cfg = McpToolConfig(mcp="data-mcp", tools=["get_data"])
        with pytest.raises(ValidationError):
            cfg.mcp = "other"

    def test_toolconfig_alias(self):
        assert ToolConfig is McpToolConfig


class TestBuiltinToolConfig:
    def test_code_interpreter(self):
        cfg = BuiltinToolConfig(builtin="code_interpreter")
        assert cfg.builtin == BuiltinToolType.CODE_INTERPRETER
        assert cfg.region is None
        assert cfg.network_mode == "PUBLIC"

    def test_browser(self):
        cfg = BuiltinToolConfig(builtin="browser")
        assert cfg.builtin == BuiltinToolType.BROWSER

    def test_with_region_override(self):
        cfg = BuiltinToolConfig(builtin="code_interpreter", region="us-west-2")
        assert cfg.region == "us-west-2"

    def test_private_network(self):
        cfg = BuiltinToolConfig(builtin="code_interpreter", network_mode="PRIVATE")
        assert cfg.network_mode == "PRIVATE"

    def test_invalid_builtin_name(self):
        with pytest.raises(ValidationError):
            BuiltinToolConfig(builtin="invalid_tool")

    def test_frozen(self):
        cfg = BuiltinToolConfig(builtin="browser")
        with pytest.raises(ValidationError):
            cfg.builtin = "code_interpreter"


class TestBuiltinToolType:
    def test_values(self):
        assert BuiltinToolType.CODE_INTERPRETER.value == "code_interpreter"
        assert BuiltinToolType.BROWSER.value == "browser"


class TestToolDeclarationUnion:
    def test_mcp_from_dict(self):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(ToolDeclaration)
        result = adapter.validate_python({"mcp": "my-mcp", "tools": ["tool1"]})
        assert isinstance(result, McpToolConfig)

    def test_builtin_from_dict(self):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(ToolDeclaration)
        result = adapter.validate_python({"builtin": "code_interpreter"})
        assert isinstance(result, BuiltinToolConfig)

    def test_browser_from_dict(self):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(ToolDeclaration)
        result = adapter.validate_python({"builtin": "browser"})
        assert isinstance(result, BuiltinToolConfig)
        assert result.builtin == BuiltinToolType.BROWSER


class TestAgentBlueprintMixedTools:
    def test_mixed_tools_accepted(self):
        bp = AgentBlueprint(
            id="test-agent",
            version="1.0.0",
            name="Test Agent",
            model={"provider": "bedrock", "model_id": "test-model"},
            prompt_ref="test-prompt",
            tools=[
                {"mcp": "data-mcp", "tools": ["query"]},
                {"builtin": "code_interpreter"},
                {"builtin": "browser"},
            ],
        )
        assert len(bp.tools) == 3
        assert isinstance(bp.tools[0], McpToolConfig)
        assert isinstance(bp.tools[1], BuiltinToolConfig)
        assert isinstance(bp.tools[2], BuiltinToolConfig)

    def test_only_builtins(self):
        bp = AgentBlueprint(
            id="test-agent",
            version="1.0.0",
            name="Test Agent",
            model={"provider": "bedrock", "model_id": "test-model"},
            prompt_ref="test-prompt",
            tools=[
                {"builtin": "code_interpreter"},
            ],
        )
        assert len(bp.tools) == 1
        assert bp.tools[0].builtin == BuiltinToolType.CODE_INTERPRETER

    def test_empty_tools(self):
        bp = AgentBlueprint(
            id="test-agent",
            version="1.0.0",
            name="Test Agent",
            model={"provider": "bedrock", "model_id": "test-model"},
            prompt_ref="test-prompt",
        )
        assert bp.tools == []
