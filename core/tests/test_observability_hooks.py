"""Tests for CompositeObservabilityHook and create_observability_hooks."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from agent_core.hooks.observability_hooks import (
    CompositeObservabilityHook,
    create_observability_hooks,
)
from agent_core.observability.langfuse_hook import reset_langfuse_client


@pytest.fixture(autouse=True)
def _reset():
    reset_langfuse_client()
    yield
    reset_langfuse_client()


class MockAuditTable:
    """Mock DynamoDB table that records put_item calls."""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def put_item(self, Item: dict, **kwargs) -> None:
        self.items.append(Item)


class TestCompositeObservabilityHook:
    def test_full_lifecycle(self, caplog: pytest.LogCaptureFixture) -> None:
        mock_table = MockAuditTable()

        hook = CompositeObservabilityHook(
            agent_id="gap_detector",
            prompt_id="gap_detector",
            prompt_version="v1.2",
            execution_mode="simulation",
            target="ENTITY-1",
        )
        # Inject mock table
        hook._audit._client = mock_table

        with caplog.at_level(logging.DEBUG, logger="agent_core.structured"):
            hook.on_agent_start()
            hook.after_model_invocation(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                input_tokens=1000,
                output_tokens=500,
            )
            hook.on_tool_end(tool_name="get_data")
            hook.on_tool_end(tool_name="bad_tool", error="timeout")
            hook.on_agent_end()

        # Verify audit events written
        assert len(mock_table.items) == 2  # PIPELINE_STARTED + PIPELINE_COMPLETED
        assert mock_table.items[0]["event_type"] == "PIPELINE_STARTED"
        assert mock_table.items[1]["event_type"] == "PIPELINE_COMPLETED"

        # Verify Langfuse summary
        summary = hook.langfuse_summary
        assert summary["generation_count"] == 1
        assert summary["total_input_tokens"] == 1000
        assert summary["total_output_tokens"] == 500

    def test_tool_error_tracking(self) -> None:
        hook = CompositeObservabilityHook(agent_id="test")
        hook._audit._client = MockAuditTable()

        hook.on_agent_start()
        hook.on_tool_end(tool_name="ok_tool")
        hook.on_tool_end(tool_name="bad_tool", error="failed")
        hook.on_tool_end(tool_name="ok_tool_2")
        hook.on_agent_end()

        assert hook._tool_calls == 3
        assert hook._tool_errors == 1

    def test_audit_failure_non_fatal(self, caplog: pytest.LogCaptureFixture) -> None:
        """Audit log failures should not crash the agent."""
        mock_table = MagicMock()
        mock_table.put_item.side_effect = RuntimeError("DynamoDB down")

        hook = CompositeObservabilityHook(agent_id="test")
        hook._audit._client = mock_table

        # Should not raise
        hook.on_agent_start()
        hook.on_agent_end()


class TestCreateObservabilityHooks:
    def test_returns_list(self) -> None:
        hooks = create_observability_hooks(
            agent_id="test",
            prompt_id="test",
            prompt_version="v1.0",
        )
        assert isinstance(hooks, list)
        assert len(hooks) == 1
        assert isinstance(hooks[0], CompositeObservabilityHook)

    def test_factory_params_propagated(self) -> None:
        hooks = create_observability_hooks(
            agent_id="gap_detector",
            prompt_id="gap_detector",
            prompt_version="v1.2",
            execution_mode="production",
            target="ENTITY-2",
            strategy_id="gap_momentum_up",
        )
        hook = hooks[0]
        assert hook.agent_id == "gap_detector"
        assert hook.execution_mode == "production"
        assert hook.target == "ENTITY-2"
        assert hook.strategy_id == "gap_momentum_up"
