"""Tests for GenericHandler session lifecycle."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent_core.runtime.agent_config import AgentConfig, AgentConfigRegistry
from agent_core.runtime.handler import GenericHandler
from agent_core.runtime.session import SessionManager


def _make_handler(
    *,
    session_manager: SessionManager | None = None,
    agent_result: object = None,
) -> tuple[GenericHandler, MagicMock]:
    """Build a GenericHandler with mocked loader and config registry.

    Returns (handler, mock_session) where mock_session is the AgentSession mock.
    """
    mock_session = MagicMock()
    mock_session.run = MagicMock(return_value=agent_result or {"output": "ok"})
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    mock_loader = MagicMock()
    mock_loader.build_agent_session.return_value = mock_session

    config = AgentConfig(
        agent_id="test_agent",
        operation_name="test_op",
        required_fields=["prompt"],
        build_prompt=lambda params, key: params.get("prompt", ""),
        defaults={},
    )
    registry = AgentConfigRegistry()
    registry.register(config)

    handler = GenericHandler(
        loader=mock_loader,
        config_registry=registry,
        idempotency_store=None,
        session_manager=session_manager,
    )
    return handler, mock_session


def _make_event(agent_id: str = "test_agent", prompt: str = "hello") -> dict:
    return {
        "agent_id": agent_id,
        "session_id": "sess-001",
        "parameters": {"prompt": prompt},
    }


class TestHandlerWithoutSessionManager:
    """GenericHandler with session_manager=None preserves Phase 3 behavior."""

    @patch("agent_core.runtime.handler.marshal_output", return_value={"raw_output": "ok"})
    def test_handler_without_session_manager(self, mock_marshal) -> None:
        handler, mock_session = _make_handler(session_manager=None)
        resp = handler.handle(_make_event())

        assert resp["statusCode"] == 200
        mock_session.run.assert_called_once()

    @patch("agent_core.runtime.handler.marshal_output", return_value={"raw_output": "ok"})
    def test_handler_uses_session_run_not_agent(self, mock_marshal) -> None:
        """Verifies session.run() is called, not session.agent()."""
        handler, mock_session = _make_handler(session_manager=None)
        handler.handle(_make_event())

        mock_session.run.assert_called_once()
        mock_session.agent.assert_not_called()


class TestHandlerWithSessionManager:
    """GenericHandler with SessionManager wires create/persist lifecycle."""

    @patch("agent_core.runtime.handler.marshal_output", return_value={"raw_output": "ok"})
    @patch("agent_core.execution.mode.get_execution_mode")
    def test_handler_with_session_manager(self, mock_mode, mock_marshal) -> None:
        mock_mode.return_value = MagicMock(value="simulation")

        sm = MagicMock(spec=SessionManager)
        sm.create_session.return_value = MagicMock()

        handler, _ = _make_handler(session_manager=sm)
        resp = handler.handle(_make_event())

        assert resp["statusCode"] == 200
        sm.create_session.assert_called_once()
        sm.persist_session.assert_called_once()

    @patch("agent_core.execution.mode.get_execution_mode")
    def test_handler_session_not_persisted_on_error(self, mock_mode) -> None:
        mock_mode.return_value = MagicMock(value="simulation")

        sm = MagicMock(spec=SessionManager)
        sm.create_session.return_value = MagicMock()

        handler, mock_session = _make_handler(session_manager=sm)
        mock_session.run.side_effect = RuntimeError("agent blew up")

        resp = handler.handle(_make_event())

        assert resp["statusCode"] == 200  # error is in body, not HTTP status
        import json
        body = json.loads(resp["body"])
        assert body["status"] == "error"
        sm.create_session.assert_called_once()
        sm.persist_session.assert_not_called()
