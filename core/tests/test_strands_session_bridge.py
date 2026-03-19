"""Tests for StrandsSessionBridge."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent_core.runtime.session import SessionState
from agent_core.runtime.strands_session_bridge import (
    StrandsSessionBridge,
    _AGENT_STATE_KEY,
    _MESSAGES_KEY,
    _MULTI_AGENT_KEY,
)


def _make_session_state(**overrides) -> SessionState:
    defaults = {
        "session_id": "test-session-001",
        "agent_id": "test-agent",
        "execution_mode": "simulation",
    }
    defaults.update(overrides)
    return SessionState(**defaults)


class TestInitialize:
    def test_restores_prior_messages(self):
        prior = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        state = _make_session_state()
        state.store(_MESSAGES_KEY, prior)

        bridge = StrandsSessionBridge(state)
        agent = SimpleNamespace(messages=[])
        bridge.initialize(agent)

        assert len(agent.messages) == 2
        assert agent.messages[0]["content"] == "hello"

    def test_no_prior_messages(self):
        state = _make_session_state()
        bridge = StrandsSessionBridge(state)
        agent = SimpleNamespace(messages=["existing"])
        bridge.initialize(agent)
        # No prior messages, agent messages unchanged
        assert agent.messages == ["existing"]


class TestAppendMessage:
    def test_accumulates_messages(self):
        state = _make_session_state()
        bridge = StrandsSessionBridge(state)
        agent = SimpleNamespace()

        bridge.append_message({"role": "user", "content": "msg1"}, agent)
        bridge.append_message({"role": "assistant", "content": "msg2"}, agent)

        assert len(bridge._messages) == 2

    def test_deep_copies_message(self):
        state = _make_session_state()
        bridge = StrandsSessionBridge(state)
        msg = {"role": "user", "content": "test"}
        bridge.append_message(msg, SimpleNamespace())
        msg["content"] = "mutated"
        assert bridge._messages[0]["content"] == "test"


class TestSyncAgent:
    def test_captures_agent_state(self):
        state = _make_session_state()
        bridge = StrandsSessionBridge(state)
        agent = SimpleNamespace(
            name="gap_detector",
            messages=[{"role": "user", "content": "analyze"}],
        )
        bridge.sync_agent(agent)
        assert bridge._agent_state["agent_name"] == "gap_detector"
        assert len(bridge._agent_state["messages"]) == 1


class TestRedactLatestMessage:
    def test_replaces_last_message(self):
        state = _make_session_state()
        bridge = StrandsSessionBridge(state)
        agent = SimpleNamespace()

        bridge.append_message({"role": "assistant", "content": "sensitive"}, agent)
        bridge.redact_latest_message({"role": "assistant", "content": "[REDACTED]"}, agent)

        assert bridge._messages[-1]["content"] == "[REDACTED]"

    def test_redact_empty_noop(self):
        state = _make_session_state()
        bridge = StrandsSessionBridge(state)
        bridge.redact_latest_message({"role": "assistant", "content": "x"}, SimpleNamespace())
        assert len(bridge._messages) == 0


class TestFlush:
    def test_writes_to_session_state(self):
        state = _make_session_state()
        bridge = StrandsSessionBridge(state)
        agent = SimpleNamespace(name="test_agent", messages=[])

        bridge.append_message({"role": "user", "content": "hello"}, agent)
        bridge.sync_agent(agent)
        bridge.flush()

        assert _MESSAGES_KEY in state.short_term
        assert len(state.short_term[_MESSAGES_KEY]) == 1
        assert _AGENT_STATE_KEY in state.short_term

    def test_pending_updates_set(self):
        state = _make_session_state()
        bridge = StrandsSessionBridge(state)
        bridge.append_message({"role": "user", "content": "test"}, SimpleNamespace())
        bridge.flush()

        pending = state.get_pending_updates()
        assert _MESSAGES_KEY in pending


class TestMultiAgent:
    def test_sync_multi_agent_captures_orchestrator(self):
        state = _make_session_state()
        bridge = StrandsSessionBridge(state)
        source = SimpleNamespace(
            name="swarm_orchestrator",
            current_agent=SimpleNamespace(name="gap_detector"),
        )
        bridge.sync_multi_agent(source)
        assert bridge._multi_agent_state["orchestrator_name"] == "swarm_orchestrator"
        assert bridge._multi_agent_state["current_agent"] == "gap_detector"

    def test_initialize_multi_agent_noop(self):
        state = _make_session_state()
        bridge = StrandsSessionBridge(state)
        bridge.initialize_multi_agent(SimpleNamespace())
        # Should not raise
