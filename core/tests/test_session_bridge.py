"""Unit tests for SFN execution ID to session ID bridge."""

from __future__ import annotations

import pytest

from agent_core.memory.session_bridge import (
    sfn_execution_id_to_session_id,
    session_id_to_sfn_execution_arn,
    extract_session_metadata,
)


class TestSessionBridge:
    """Tests for session ID conversion."""

    def test_arn_to_session_id(self):
        arn = "arn:aws:states:eu-west-1:123456789012:execution:my-dev-workflow:exec-abc123"
        assert sfn_execution_id_to_session_id(arn) == "exec-abc123"

    def test_plain_id_passthrough(self):
        assert sfn_execution_id_to_session_id("exec-abc123") == "exec-abc123"

    def test_session_id_to_arn(self):
        arn = session_id_to_sfn_execution_arn(
            "exec-abc123",
            "my-dev-workflow",
            region="eu-west-1",
            account_id="123456789012",
        )
        assert arn == (
            "arn:aws:states:eu-west-1:123456789012:"
            "execution:my-dev-workflow:exec-abc123"
        )

    def test_extract_session_metadata(self):
        execution_input = {
            "_sfn_context": {
                "Execution": {
                    "Id": "arn:aws:states:eu-west-1:123456789012:execution:my-dev-workflow:exec-xyz",
                    "StartTime": "2026-03-15T08:30:00Z",
                },
                "StateMachine": {
                    "Id": "arn:aws:states:eu-west-1:123456789012:stateMachine:my-dev-workflow",
                },
            },
        }
        metadata = extract_session_metadata(execution_input)

        assert metadata["session_id"] == "exec-xyz"
        assert metadata["start_time"] == "2026-03-15T08:30:00Z"

    def test_extract_session_metadata_fallback(self):
        execution_input = {"session_id": "manual-session"}
        metadata = extract_session_metadata(execution_input)
        assert metadata["session_id"] == "manual-session"
