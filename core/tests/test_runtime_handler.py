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

    def test_handler_threads_event_mode_into_session(self, monkeypatch) -> None:
        """payload.execution_mode must be forwarded to create_session, not env default."""
        import os
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("EXECUTION_MODE", "simulation")

        mock_session_mgr = MagicMock()
        mock_session_mgr.create_session.return_value = MagicMock()
        mock_session_mgr.persist_session.return_value = None

        mock_agent_session = MagicMock()
        mock_agent_session.__enter__ = MagicMock(return_value=mock_agent_session)
        mock_agent_session.__exit__ = MagicMock(return_value=False)
        mock_agent_session.run.return_value = "ok"

        mock_loader = MagicMock()
        mock_loader.build_agent_session.return_value = mock_agent_session
        mock_loader.load_agent.return_value = MagicMock(
            artifacts=MagicMock(tier="platform", kms_key_alias=None)
        )

        mock_config = MagicMock()
        mock_config.defaults = {}
        mock_config.required_fields = []
        mock_config.operation_name = "op"
        mock_config.build_prompt.return_value = "prompt"

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_config

        from agent_core.runtime.handler import GenericHandler

        handler = GenericHandler(
            loader=mock_loader,
            config_registry=mock_registry,
            session_manager=mock_session_mgr,
        )
        handler.handle({
            "agent_id": "gap-detector",
            "execution_mode": "production",
            "input": {"prompt": "x"},
        })

        mock_session_mgr.create_session.assert_called_once()
        _, kwargs = mock_session_mgr.create_session.call_args
        assert kwargs.get("execution_mode") == "production", (
            f"Expected 'production' but got {kwargs.get('execution_mode')!r} — "
            "handler is not forwarding payload.execution_mode to create_session"
        )
