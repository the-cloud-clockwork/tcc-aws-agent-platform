"""Unit tests for AgentCore entrypoint — AgentCoreApp and @register_agent."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from agent_core.runtime.adapter import AgentResult
from agent_core.runtime.entrypoint import (
    _AGENT_REGISTRY,
    AgentCoreApp,
    get_registered_agents,
    register_agent,
)


@pytest.fixture(autouse=True)
def clear_registry():
    """Clear agent registry between tests."""
    _AGENT_REGISTRY.clear()
    yield
    _AGENT_REGISTRY.clear()


class TestRegisterAgent:
    """Tests for the @register_agent decorator."""

    def test_register_and_retrieve(self):
        @register_agent("test-agent")
        def my_handler(payload, session):
            return AgentResult(
                status="success",
                agent_id="test-agent",
                session_id=payload.session_id,
                output={"result": "ok"},
            )

        agents = get_registered_agents()
        assert "test-agent" in agents
        assert agents["test-agent"] == my_handler

    def test_register_multiple_agents(self):
        @register_agent("agent-a")
        def handler_a(payload, session):
            pass

        @register_agent("agent-b")
        def handler_b(payload, session):
            pass

        agents = get_registered_agents()
        assert len(agents) == 2


class TestAgentCoreApp:
    """Tests for AgentCoreApp invoke method."""

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_invoke_lambda_mode(self):
        @register_agent("test-agent")
        def my_handler(payload, session):
            return AgentResult(
                status="success",
                agent_id="test-agent",
                session_id=payload.session_id,
                output={"result": "ok"},
            )

        app = AgentCoreApp()
        response = app.invoke(
            {
                "agent_id": "test-agent",
                "session_id": "s123",
                "date": "2026-03-15",
            }
        )

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["result"] == "ok"

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_invoke_unknown_agent(self):
        app = AgentCoreApp()
        response = app.invoke(
            {
                "agent_id": "nonexistent-agent",
                "session_id": "s123",
            }
        )

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "nonexistent-agent" in body["error"]

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_invoke_handler_exception(self):
        @register_agent("failing-agent")
        def my_handler(payload, session):
            raise RuntimeError("Agent crashed")

        app = AgentCoreApp()
        response = app.invoke(
            {
                "agent_id": "failing-agent",
                "session_id": "s123",
            }
        )

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "Agent crashed" in body["error"]

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_invoke_with_memory_updates(self):
        @register_agent("memory-agent")
        def my_handler(payload, session):
            session.store("key", "value")
            return AgentResult(
                status="success",
                agent_id="memory-agent",
                session_id=payload.session_id,
                output={"result": "ok"},
                memory_updates=session.get_pending_updates(),
            )

        app = AgentCoreApp()
        response = app.invoke(
            {
                "agent_id": "memory-agent",
                "session_id": "s123",
            }
        )

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body.get("_memory_updates") == {"key": "value"}

    @patch.dict(os.environ, {"RUNTIME_MODE": "lambda"})
    def test_invoke_with_generic_handler(self):
        """When a handler is provided, invoke delegates to it."""

        class MockHandler:
            def handle(self, event, context=None):
                return {"statusCode": 200, "body": '{"delegated": true}'}

        app = AgentCoreApp(handler=MockHandler())
        response = app.invoke({"agent_id": "any"})

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["delegated"] is True
