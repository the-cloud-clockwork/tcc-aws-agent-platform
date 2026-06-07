"""Tests for Bug H — Langfuse reasoning content capture.

The token-only metadata path left every Langfuse trace with ``input: null`` /
``output: null``. ``CompositeObservabilityHook._on_after_invocation`` now
extracts the conversation from ``agent.messages`` and threads it to the
LangfuseHook so the prompt, reasoning, tool I/O, and final answer are captured.

These tests exercise the content-extraction helpers and assert that
``_on_after_invocation`` passes ``input_text`` / ``output_text`` through to
the (mocked) LangfuseHook. The legacy callbacks remain ``**kwargs``
pass-throughs, so this is purely additive.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent_core.hooks.observability_hooks import CompositeObservabilityHook


# ---- representative conversation -------------------------------------------

PROMPT = "Analyze gaps for 2026-05-22"
FINAL = "Final: AAPL gapped 3%."

CONVERSATION = [
    {"role": "user", "content": [{"text": PROMPT}]},
    {
        "role": "assistant",
        "content": [
            {"text": "Let me check the gap."},
            {"toolUse": {"name": "get_gap", "input": {"symbol": "AAPL"}}},
        ],
    },
    {"role": "user", "content": [{"toolResult": {"content": [{"text": "gap 3%"}]}}]},
    {"role": "assistant", "content": [{"text": FINAL}]},
]


def _hook() -> CompositeObservabilityHook:
    """A composite hook with all three sub-sinks mocked out."""
    hook = CompositeObservabilityHook(agent_id="gap-detector", prompt_id="gap-detector")
    hook._langfuse = MagicMock()
    hook._langfuse.summary = {
        "generation_count": 1,
        "total_input_tokens": 10,
        "total_output_tokens": 5,
        "total_cost_usd": 0.0,
    }
    hook._audit = MagicMock()
    hook._logger = MagicMock()
    return hook


def _event(messages: list, *, in_tokens: int = 10, out_tokens: int = 5) -> SimpleNamespace:
    """Fake Strands AfterInvocationEvent carrying an agent."""
    model = MagicMock()
    model.get_config.return_value = {"model_id": "claude-max-opus"}
    agent = SimpleNamespace(
        messages=messages,
        event_loop_metrics=SimpleNamespace(
            accumulated_usage={"inputTokens": in_tokens, "outputTokens": out_tokens}
        ),
        model=model,
    )
    return SimpleNamespace(agent=agent)


# ---- helper unit tests ------------------------------------------------------

def test_extract_prompt_returns_first_user_text():
    assert CompositeObservabilityHook._extract_prompt(CONVERSATION) == PROMPT


def test_extract_prompt_skips_toolresult_only_user_messages():
    # The 3rd message is a user toolResult with no text block — must be skipped,
    # and since it follows the real prompt the first match still wins.
    msgs = [
        {"role": "user", "content": [{"toolResult": {"content": [{"text": "x"}]}}]},
        {"role": "user", "content": [{"text": "real prompt"}]},
    ]
    assert CompositeObservabilityHook._extract_prompt(msgs) == "real prompt"


def test_extract_final_output_returns_last_assistant_text():
    assert CompositeObservabilityHook._extract_final_output(CONVERSATION) == FINAL


def test_extract_helpers_empty_on_no_match():
    assert CompositeObservabilityHook._extract_prompt([]) == ""
    assert CompositeObservabilityHook._extract_final_output([]) == ""
    # assistant turn with only a toolUse (no text) yields no final output
    assert (
        CompositeObservabilityHook._extract_final_output(
            [{"role": "assistant", "content": [{"toolUse": {"name": "t"}}]}]
        )
        == ""
    )


def test_conversation_json_roundtrips_and_caps():
    out = CompositeObservabilityHook._conversation_json(CONVERSATION)
    assert json.loads(out) == CONVERSATION
    assert "get_gap" in out  # tool I/O preserved
    big = [{"role": "user", "content": [{"text": "x" * 500_000}]}]
    assert len(CompositeObservabilityHook._conversation_json(big)) <= 200_000


# ---- wiring tests -----------------------------------------------------------

def test_after_invocation_threads_content_to_langfuse():
    hook = _hook()
    hook._on_after_invocation(_event(CONVERSATION))

    # generation gets the full conversation JSON + final answer
    hook._langfuse.after_model_invocation.assert_called_once()
    amc = hook._langfuse.after_model_invocation.call_args.kwargs
    assert amc["model_id"] == "claude-max-opus"
    assert amc["input_tokens"] == 10
    assert amc["output_tokens"] == 5
    assert json.loads(amc["input_text"]) == CONVERSATION
    assert amc["output_text"] == FINAL

    # trace gets prompt as input, final answer as output
    hook._langfuse.on_agent_end.assert_called_once()
    end = hook._langfuse.on_agent_end.call_args.kwargs
    assert end["input_text"] == PROMPT
    assert end["output_text"] == FINAL


def test_after_invocation_without_agent_is_safe():
    hook = _hook()
    hook._on_after_invocation(SimpleNamespace())  # no .agent

    hook._langfuse.after_model_invocation.assert_not_called()
    hook._langfuse.on_agent_end.assert_called_once()
    end = hook._langfuse.on_agent_end.call_args.kwargs
    assert end["input_text"] == ""
    assert end["output_text"] == ""


def test_after_invocation_without_messages_still_finalises():
    hook = _hook()
    agent = SimpleNamespace(
        messages=[],
        event_loop_metrics=SimpleNamespace(accumulated_usage={"inputTokens": 1, "outputTokens": 1}),
        model=MagicMock(get_config=MagicMock(return_value={"model_id": "m"})),
    )
    hook._on_after_invocation(SimpleNamespace(agent=agent))

    amc = hook._langfuse.after_model_invocation.call_args.kwargs
    assert amc["input_text"] == "[]"  # empty conversation JSON
    assert amc["output_text"] == ""
    end = hook._langfuse.on_agent_end.call_args.kwargs
    assert end["input_text"] == ""
    assert end["output_text"] == ""


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
