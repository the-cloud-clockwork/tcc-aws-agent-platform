"""Tests for ObservabilityHook and ConstraintHook."""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from agent_core.hooks.constraints import ConstraintHook
from agent_core.hooks.observability import ObservabilityHook

if TYPE_CHECKING:
    import pytest


class TestObservabilityHook:
    def test_lifecycle(self, caplog: pytest.LogCaptureFixture) -> None:
        hook = ObservabilityHook(agent_id="test_agent", execution_mode="simulation")

        with caplog.at_level(logging.INFO, logger="agent_core.observability"):
            hook.on_agent_start()
            hook.on_tool_end(tool_name="get_data")
            hook.on_tool_end(tool_name="bad_tool", error="timeout")
            hook.on_agent_end()

        messages = [r.message for r in caplog.records]
        assert len(messages) == 4

        # Verify agent_start
        start = json.loads(messages[0])
        assert start["event"] == "agent_start"
        assert start["agent_id"] == "test_agent"

        # Verify tool_end (success)
        tool_ok = json.loads(messages[1])
        assert tool_ok["event"] == "tool_end"
        assert tool_ok["tool_name"] == "get_data"
        assert "error" not in tool_ok

        # Verify tool_end (error)
        tool_err = json.loads(messages[2])
        assert tool_err["event"] == "tool_end"
        assert tool_err["error"] == "timeout"
        assert tool_err["level"] == "ERROR"

        # Verify agent_end
        end = json.loads(messages[3])
        assert end["event"] == "agent_end"
        assert end["tool_calls"] == 2
        assert end["tool_errors"] == 1
        assert end["elapsed_seconds"] >= 0

    def test_default_agent_id(self) -> None:
        hook = ObservabilityHook()
        assert hook.agent_id == "unknown"


class TestConstraintHook:
    def test_trims_excess_recommendations(self) -> None:
        hook = ConstraintHook(max_recommendations=2)
        result = {
            "recommendations": [
                {"target": "AAPL"},
                {"target": "GOOGL"},
                {"target": "TSLA"},
                {"target": "MSFT"},
            ]
        }
        trimmed = hook.on_agent_end(result=result)
        assert trimmed is not None
        assert len(trimmed["recommendations"]) == 2
        assert trimmed["recommendations"][0]["target"] == "AAPL"

    def test_no_trim_when_within_limit(self) -> None:
        hook = ConstraintHook(max_recommendations=5)
        result = {"recommendations": [{"target": "AAPL"}]}
        out = hook.on_agent_end(result=result)
        assert out is not None
        assert len(out["recommendations"]) == 1

    def test_none_result(self) -> None:
        hook = ConstraintHook()
        assert hook.on_agent_end(result=None) is None

    def test_no_recommendations_key(self) -> None:
        hook = ConstraintHook()
        result: dict = {"other_key": 42}
        out = hook.on_agent_end(result=result)
        assert out == {"other_key": 42}
