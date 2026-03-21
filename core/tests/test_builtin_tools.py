"""Tests for builtin tool providers and wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent_core.schemas.tool_config import BuiltinToolConfig


class TestCodeInterpreterProvider:
    @patch("agent_core.tools.code_interpreter.CodeInterpreter")
    def test_creates_client_with_region(self, mock_ci_cls):
        from agent_core.tools.code_interpreter import CodeInterpreterProvider

        provider = CodeInterpreterProvider(region="us-east-1")
        mock_ci_cls.assert_called_once_with("us-east-1")
        assert provider._region == "us-east-1"

    @patch("agent_core.tools.code_interpreter.CodeInterpreter")
    def test_start_delegates(self, mock_ci_cls):
        from agent_core.tools.code_interpreter import CodeInterpreterProvider

        mock_client = MagicMock()
        mock_ci_cls.return_value = mock_client

        provider = CodeInterpreterProvider(region="us-east-1")
        provider.start()
        mock_client.start.assert_called_once()

    @patch("agent_core.tools.code_interpreter.CodeInterpreter")
    def test_stop_delegates(self, mock_ci_cls):
        from agent_core.tools.code_interpreter import CodeInterpreterProvider

        mock_client = MagicMock()
        mock_ci_cls.return_value = mock_client

        provider = CodeInterpreterProvider(region="us-east-1")
        provider.start()
        provider.stop()
        mock_client.stop.assert_called_once()

    @patch("agent_core.tools.code_interpreter.CodeInterpreter")
    def test_stop_idempotent(self, mock_ci_cls):
        from agent_core.tools.code_interpreter import CodeInterpreterProvider

        mock_client = MagicMock()
        mock_ci_cls.return_value = mock_client

        provider = CodeInterpreterProvider(region="us-east-1")
        # stop without start should be no-op
        provider.stop()
        mock_client.stop.assert_not_called()

    @patch("agent_core.tools.code_interpreter.CodeInterpreter")
    def test_tools_returns_five_callables(self, mock_ci_cls):
        from agent_core.tools.code_interpreter import CodeInterpreterProvider

        provider = CodeInterpreterProvider(region="us-east-1")
        tools = provider.tools
        assert len(tools) == 5
        names = {t.__name__ for t in tools}
        assert names == {
            "execute_code",
            "execute_command",
            "write_files",
            "list_files",
            "read_file",
        }


class TestBrowserProvider:
    @patch("agent_core.tools.browser.AgentCoreBrowser")
    def test_creates_browser_with_region(self, mock_browser_cls):
        from agent_core.tools.browser import BrowserProvider

        mock_instance = MagicMock()
        mock_browser_cls.return_value = mock_instance

        BrowserProvider(region="us-west-2")
        mock_browser_cls.assert_called_once_with(region="us-west-2")

    @patch("agent_core.tools.browser.AgentCoreBrowser")
    def test_tools_returns_one_callable(self, mock_browser_cls):
        from agent_core.tools.browser import BrowserProvider

        mock_instance = MagicMock()
        mock_instance.browser = MagicMock()
        mock_browser_cls.return_value = mock_instance

        provider = BrowserProvider(region="us-west-2")
        tools = provider.tools
        assert len(tools) == 1
        assert tools[0] is mock_instance.browser

    @patch("agent_core.tools.browser.AgentCoreBrowser")
    def test_start_stop_noop(self, mock_browser_cls):
        from agent_core.tools.browser import BrowserProvider

        provider = BrowserProvider(region="us-west-2")
        provider.start()
        provider.stop()


class TestBuiltinToolWiring:
    @patch("agent_core.tools.wiring.CodeInterpreterProvider")
    def test_creates_code_interpreter(self, mock_ci_cls):
        from agent_core.tools.wiring import BuiltinToolWiring

        mock_provider = MagicMock()
        mock_provider.tools = [MagicMock(), MagicMock()]
        mock_ci_cls.return_value = mock_provider

        configs = [BuiltinToolConfig(builtin="code_interpreter")]
        wiring = BuiltinToolWiring(configs=configs, region="us-east-1")

        mock_ci_cls.assert_called_once_with(region="us-east-1", network_mode="PUBLIC")
        assert len(wiring.tool_providers) == 2

    @patch("agent_core.tools.wiring.BrowserProvider")
    def test_creates_browser(self, mock_browser_cls):
        from agent_core.tools.wiring import BuiltinToolWiring

        mock_provider = MagicMock()
        mock_provider.tools = [MagicMock()]
        mock_browser_cls.return_value = mock_provider

        configs = [BuiltinToolConfig(builtin="browser")]
        wiring = BuiltinToolWiring(configs=configs, region="us-west-2")

        mock_browser_cls.assert_called_once_with(region="us-west-2")
        assert len(wiring.tool_providers) == 1

    @patch("agent_core.tools.wiring.BrowserProvider")
    @patch("agent_core.tools.wiring.CodeInterpreterProvider")
    def test_mixed_providers(self, mock_ci_cls, mock_browser_cls):
        from agent_core.tools.wiring import BuiltinToolWiring

        mock_ci = MagicMock()
        mock_ci.tools = [MagicMock()] * 5
        mock_ci_cls.return_value = mock_ci

        mock_browser = MagicMock()
        mock_browser.tools = [MagicMock()]
        mock_browser_cls.return_value = mock_browser

        configs = [
            BuiltinToolConfig(builtin="code_interpreter"),
            BuiltinToolConfig(builtin="browser"),
        ]
        wiring = BuiltinToolWiring(configs=configs, region="us-east-1")
        assert len(wiring.tool_providers) == 6

    @patch("agent_core.tools.wiring.CodeInterpreterProvider")
    def test_region_override(self, mock_ci_cls):
        from agent_core.tools.wiring import BuiltinToolWiring

        mock_ci_cls.return_value = MagicMock(tools=[])

        configs = [
            BuiltinToolConfig(builtin="code_interpreter", region="ap-southeast-1")
        ]
        BuiltinToolWiring(configs=configs, region="us-east-1")

        mock_ci_cls.assert_called_once_with(
            region="ap-southeast-1", network_mode="PUBLIC"
        )

    @patch("agent_core.tools.wiring.CodeInterpreterProvider")
    def test_start_propagates(self, mock_ci_cls):
        from agent_core.tools.wiring import BuiltinToolWiring

        mock_provider = MagicMock(tools=[])
        mock_ci_cls.return_value = mock_provider

        configs = [BuiltinToolConfig(builtin="code_interpreter")]
        wiring = BuiltinToolWiring(configs=configs, region="us-east-1")
        wiring.start()

        mock_provider.start.assert_called_once()

    @patch("agent_core.tools.wiring.CodeInterpreterProvider")
    def test_stop_exception_safe(self, mock_ci_cls):
        from agent_core.tools.wiring import BuiltinToolWiring

        mock_provider = MagicMock(tools=[])
        mock_provider.stop.side_effect = RuntimeError("stop failed")
        mock_ci_cls.return_value = mock_provider

        configs = [BuiltinToolConfig(builtin="code_interpreter")]
        wiring = BuiltinToolWiring(configs=configs, region="us-east-1")
        # Should not raise
        wiring.stop()


class TestAgentSessionBuiltinLifecycle:
    def test_session_starts_and_stops_builtin_wiring(self):
        from agent_core.blueprints.session import AgentSession

        mock_agent = MagicMock()
        mock_wiring = MagicMock()

        session = AgentSession(
            agent=mock_agent,
            mcp_clients=[],
            builtin_wiring=mock_wiring,
        )

        with session:
            mock_wiring.start.assert_called_once()

        mock_wiring.stop.assert_called_once()

    def test_session_without_builtin_wiring(self):
        from agent_core.blueprints.session import AgentSession

        mock_agent = MagicMock()
        session = AgentSession(agent=mock_agent, mcp_clients=[])

        with session:
            pass  # Should not raise

    def test_session_builtin_property(self):
        from agent_core.blueprints.session import AgentSession

        mock_agent = MagicMock()
        mock_wiring = MagicMock()

        session = AgentSession(
            agent=mock_agent,
            mcp_clients=[],
            builtin_wiring=mock_wiring,
        )
        assert session.builtin is mock_wiring

    def test_session_builtin_property_none(self):
        from agent_core.blueprints.session import AgentSession

        session = AgentSession(agent=MagicMock(), mcp_clients=[])
        assert session.builtin is None
