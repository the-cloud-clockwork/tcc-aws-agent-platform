"""Tests for agent_core.runtime.adapter — AgentResult dataclass."""

from __future__ import annotations


class TestAgentResult:
    """Test AgentResult dataclass and serialization."""

    def test_minimal_construction(self) -> None:
        from agent_core.runtime.adapter import AgentResult

        result = AgentResult(status="success", agent_id="a1", session_id="s1")
        assert result.status == "success"
        assert result.agent_id == "a1"
        assert result.session_id == "s1"
        assert result.output == {}
        assert result.error is None
        assert result.claim_check is None

    def test_full_construction(self) -> None:
        from agent_core.runtime.adapter import AgentResult

        result = AgentResult(
            status="success",
            agent_id="a1",
            session_id="s1",
            output={"key": "val"},
            metadata={"m": 1},
            error=None,
            claim_check="ck-123",
            artifact_id="art-456",
            s3_key="s3://bucket/key",
            tier="GOLD",
        )
        assert result.claim_check == "ck-123"
        assert result.artifact_id == "art-456"
        assert result.s3_key == "s3://bucket/key"
        assert result.tier == "GOLD"

    def test_to_response(self) -> None:
        from agent_core.runtime.adapter import AgentResult

        result = AgentResult(
            status="success",
            agent_id="a1",
            session_id="s1",
            output={"answer": "42"},
        )
        resp = result.to_response()
        assert isinstance(resp, dict)
        assert resp["status"] == "success"
        assert resp["agent_id"] == "a1"

    def test_error_result(self) -> None:
        from agent_core.runtime.adapter import AgentResult

        result = AgentResult(
            status="error",
            agent_id="a1",
            session_id="s1",
            error="something broke",
        )
        assert result.error == "something broke"
        resp = result.to_response()
        assert resp["status"] == "error"
