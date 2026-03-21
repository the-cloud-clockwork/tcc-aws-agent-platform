"""Tests for agent_core.runtime.handler — GenericHandler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestGenericHandler:
    """Test GenericHandler dispatch and error handling."""

    @patch("agent_core.runtime.handler.SessionManager")
    @patch("agent_core.runtime.handler.AgentConfigRegistry")
    @patch("agent_core.runtime.handler.BlueprintLoader")
    def test_construction(
        self, mock_loader: MagicMock, mock_registry: MagicMock, mock_sm: MagicMock
    ) -> None:
        from agent_core.runtime.handler import GenericHandler

        handler = GenericHandler(
            loader=mock_loader,
            config_registry=mock_registry,
        )
        assert handler is not None

    @patch("agent_core.runtime.handler.SessionManager")
    @patch("agent_core.runtime.handler.AgentConfigRegistry")
    @patch("agent_core.runtime.handler.BlueprintLoader")
    def test_handle_returns_dict(
        self, mock_loader: MagicMock, mock_registry: MagicMock, mock_sm: MagicMock
    ) -> None:
        from agent_core.runtime.handler import GenericHandler

        mock_registry.resolve.return_value = MagicMock(
            agent_id="test-agent",
            blueprint_id="test-bp",
        )

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value = "test output"
        mock_loader.build_agent_session.return_value = mock_session

        handler = GenericHandler(
            loader=mock_loader,
            config_registry=mock_registry,
        )
        result = handler.handle({"prompt": "hello", "agent_id": "test-agent"})
        assert isinstance(result, dict)

    @patch("agent_core.runtime.handler.SessionManager")
    @patch("agent_core.runtime.handler.AgentConfigRegistry")
    @patch("agent_core.runtime.handler.BlueprintLoader")
    def test_handle_missing_prompt(
        self, mock_loader: MagicMock, mock_registry: MagicMock, mock_sm: MagicMock
    ) -> None:
        from agent_core.runtime.handler import GenericHandler

        mock_registry.resolve.return_value = MagicMock(agent_id="a1")
        handler = GenericHandler(loader=mock_loader, config_registry=mock_registry)
        result = handler.handle({})
        assert isinstance(result, dict)
