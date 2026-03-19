"""Tests for A2A protocol models, discovery, and task handler."""

from __future__ import annotations

import pytest

from agent_core.a2a.discovery import AgentDiscovery, DiscoveredAgent
from agent_core.a2a.models import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    Task,
    TaskMessage,
    TaskState,
    TaskStatus,
)
from agent_core.a2a.task_handler import A2ATaskHandler


class TestA2AModels:
    """Tests for A2A Pydantic models."""

    def test_agent_card_creation(self):
        card = AgentCard(
            name="Test Agent",
            description="A test agent",
            url="http://localhost:8080/agents/test",
            skills=[
                AgentSkill(
                    id="do_thing",
                    name="Do Thing",
                    description="Does a thing",
                    tags=["test"],
                ),
            ],
            provider={"organization": "TestOrg", "url": "https://test.example.com"},
        )
        assert card.name == "Test Agent"
        assert card.protocol_version == "0.2.1"
        assert len(card.skills) == 1
        assert card.provider["organization"] == "TestOrg"

    def test_agent_card_no_default_provider(self):
        """Provider defaults to empty dict (no hardcoded org)."""
        card = AgentCard(
            name="Test",
            description="Test",
            url="http://localhost",
        )
        assert card.provider == {}

    def test_agent_card_roundtrip(self):
        card = AgentCard(
            name="Roundtrip Agent",
            description="Test roundtrip",
            url="http://test.example.com",
            provider={"organization": "Test"},
        )
        data = card.model_dump()
        card2 = AgentCard(**data)
        assert card2.name == card.name
        assert card2.url == card.url

    def test_task_state_enum(self):
        assert TaskState.SUBMITTED == "submitted"
        assert TaskState.COMPLETED == "completed"
        assert len(TaskState) == 6

    def test_task_creation(self):
        task = Task(
            status=TaskStatus(state=TaskState.SUBMITTED),
            messages=[TaskMessage(role="user", parts=[{"type": "text", "text": "hello"}])],
        )
        assert task.status.state == TaskState.SUBMITTED
        assert len(task.messages) == 1
        assert task.id  # auto-generated


class TestTaskHandler:
    """Tests for A2ATaskHandler."""

    @pytest.fixture
    def mock_handler(self):
        def handler(event):
            return {
                "statusCode": 200,
                "body": '{"result": "success", "summary": "Test completed."}',
            }

        return handler

    @pytest.fixture
    def task_handler(self, mock_handler):
        return A2ATaskHandler(agent_handlers={"test-agent": mock_handler})

    def test_send_task_success(self, task_handler):
        request = {
            "id": "task-001",
            "message": {
                "parts": [{"type": "data", "data": {"date": "2026-03-15"}}],
            },
        }
        task = task_handler.send_task("test-agent", request)
        assert task.id == "task-001"
        assert task.status.state == TaskState.COMPLETED
        assert len(task.messages) == 2  # user + agent

    def test_send_task_unknown_agent(self, task_handler):
        request = {"message": {"parts": []}}
        task = task_handler.send_task("nonexistent-agent", request)
        assert task.status.state == TaskState.FAILED

    def test_get_task(self, task_handler):
        request = {"id": "task-002", "message": {"parts": []}}
        task_handler.send_task("test-agent", request)
        task = task_handler.get_task("task-002")
        assert task is not None
        assert task.id == "task-002"

    def test_cancel_task(self, task_handler):
        request = {"id": "task-003", "message": {"parts": []}}
        task_handler.send_task("test-agent", request)
        task = task_handler.cancel_task("task-003")
        assert task is not None
        # Task already completed, so state stays completed
        assert task.status.state == TaskState.COMPLETED

    def test_optional_blueprint_loader(self):
        """Task handler accepts an optional blueprint_loader."""
        handler = A2ATaskHandler(
            agent_handlers={},
            blueprint_loader="mock_loader",
        )
        assert handler._loader == "mock_loader"


class TestDiscovery:
    """Tests for AgentDiscovery."""

    def test_find_by_skill_empty(self):
        discovery = AgentDiscovery()
        results = discovery.find_by_skill("trading")
        assert len(results) == 0

    def test_list_cached_empty(self):
        discovery = AgentDiscovery()
        assert len(discovery.list_cached()) == 0

    def test_get_cached_miss(self):
        discovery = AgentDiscovery()
        assert discovery.get_cached("http://nonexistent") is None

    def test_find_by_skill_with_cached(self):
        discovery = AgentDiscovery()
        card = AgentCard(
            name="Test",
            description="Test",
            url="http://test",
            skills=[AgentSkill(id="s1", name="S1", description="S1", tags=["trading"])],
        )
        discovery._cache["http://test"] = DiscoveredAgent(card=card, health_status="healthy")
        results = discovery.find_by_skill("trading")
        assert len(results) == 1
