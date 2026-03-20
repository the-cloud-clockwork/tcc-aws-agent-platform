"""Tests for LangfuseHook.

Tests run without a real Langfuse instance -- they verify the hook's
internal tracking logic (token counts, cost, summary) and that errors
from Langfuse are handled gracefully.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from agent_core.observability.langfuse_hook import (
    LangfuseHook,
    reset_langfuse_client,
)


@pytest.fixture(autouse=True)
def _reset_langfuse():
    """Reset the global Langfuse client before each test."""
    reset_langfuse_client()
    yield
    reset_langfuse_client()


class TestLangfuseHook:
    def test_lifecycle_without_langfuse(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify hook tracks metrics even when Langfuse is not available."""
        hook = LangfuseHook(
            agent_id="test_detector",
            prompt_id="test_detector",
            prompt_version="v1.2",
            execution_mode="simulation",
            target="ENTITY-1",
        )

        with caplog.at_level(logging.INFO, logger="agent_core.langfuse"):
            hook.on_agent_start()
            hook.after_model_invocation(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                input_tokens=1000,
                output_tokens=500,
                stop_reason="end_turn",
            )
            hook.after_model_invocation(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                input_tokens=800,
                output_tokens=300,
                stop_reason="tool_use",
            )
            hook.on_agent_end()

        summary = hook.summary
        assert summary["agent_id"] == "test_detector"
        assert summary["generation_count"] == 2
        assert summary["total_input_tokens"] == 1800
        assert summary["total_output_tokens"] == 800
        assert summary["total_cost_usd"] > 0

    def test_tags(self) -> None:
        hook = LangfuseHook(
            agent_id="analytics",
            prompt_id="analytics",
            prompt_version="v2.0",
            execution_mode="production",
            target="ENTITY-2",
            strategy_id="multi_signal_entry",
        )
        tags = hook._tags()
        assert tags["agent_id"] == "analytics"
        assert tags["target"] == "ENTITY-2"
        assert tags["strategy_id"] == "multi_signal_entry"

    def test_tags_without_optional_fields(self) -> None:
        hook = LangfuseHook(agent_id="test")
        tags = hook._tags()
        assert "target" not in tags
        assert "strategy_id" not in tags

    def test_summary_initial_state(self) -> None:
        hook = LangfuseHook(agent_id="test")
        summary = hook.summary
        assert summary["generation_count"] == 0
        assert summary["total_input_tokens"] == 0
        assert summary["total_cost_usd"] == 0.0

    @patch("agent_core.observability.langfuse_hook._get_langfuse_client")
    def test_with_mock_langfuse(self, mock_get_client: MagicMock) -> None:
        """Verify Langfuse client methods are called correctly."""
        mock_client = MagicMock()
        mock_trace = MagicMock()
        mock_client.trace.return_value = mock_trace
        mock_get_client.return_value = mock_client

        hook = LangfuseHook(agent_id="test_agent")
        hook.on_agent_start()
        hook.after_model_invocation(
            model_id="test-model",
            input_tokens=100,
            output_tokens=50,
        )
        hook.on_agent_end()

        # Verify trace was created
        mock_client.trace.assert_called_once()
        # Verify generation was logged
        mock_trace.generation.assert_called_once()
        # Verify trace was updated
        mock_trace.update.assert_called_once()
        # Verify flush was called
        mock_client.flush.assert_called_once()

    def test_cost_accumulation(self) -> None:
        hook = LangfuseHook(agent_id="cost_test")
        hook.on_agent_start()

        # 3 invocations of Sonnet
        for _ in range(3):
            hook.after_model_invocation(
                model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                input_tokens=1000,
                output_tokens=500,
            )

        summary = hook.summary
        assert summary["generation_count"] == 3
        assert summary["total_input_tokens"] == 3000
        assert summary["total_output_tokens"] == 1500
        # 3 * ($0.003 + $0.0075) = $0.0315
        assert abs(summary["total_cost_usd"] - 0.0315) < 1e-6
