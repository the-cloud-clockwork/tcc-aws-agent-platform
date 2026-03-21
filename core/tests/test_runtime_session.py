"""Tests for agent_core.runtime.session — SessionManager + SessionState."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestSessionState:
    """Test SessionState data container."""

    def test_construction(self) -> None:
        from agent_core.runtime.session import SessionState

        state = SessionState(
            session_id="s1",
            agent_id="a1",
            execution_mode="AGENTCORE",
        )
        assert state.session_id == "s1"
        assert state.agent_id == "a1"
        assert state.execution_mode == "AGENTCORE"


class TestSessionManager:
    """Test SessionManager lifecycle operations."""

    @patch("agent_core.runtime.session.boto3")
    def test_create_session(self, mock_boto: MagicMock) -> None:
        from agent_core.runtime.session import SessionManager

        mgr = SessionManager()
        state = mgr.create_session(
            session_id="s1",
            agent_id="a1",
            execution_mode="AGENTCORE",
        )
        assert state.session_id == "s1"

    @patch("agent_core.runtime.session.boto3")
    def test_persist_session(self, mock_boto: MagicMock) -> None:
        from agent_core.runtime.session import SessionManager, SessionState

        mgr = SessionManager()
        state = SessionState(
            session_id="s1",
            agent_id="a1",
            execution_mode="AGENTCORE",
        )
        mgr.persist_session(state)
