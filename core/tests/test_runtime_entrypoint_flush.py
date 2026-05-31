"""Tests for the telemetry-flush wrapper in agent_core.runtime.entrypoint.

Regression guard for Bug G: agent microVMs are suspended immediately after
responding, so buffered OTel logs/metrics must be force-flushed at the end of
every invocation. `_wrap_with_flush` must call `_flush_telemetry` once the
handler (or its streamed output) completes — for all four handler shapes —
and must preserve the handler signature so the SDK still injects `context`.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from agent_core.runtime.entrypoint import _wrap_with_flush


def test_signature_preserved_for_context_detection() -> None:
    """SDK `_takes_context` checks `params[1] == 'context'` via inspect.signature."""

    def handler(payload, context):  # noqa: ANN001, ANN202
        return None

    wrapped = _wrap_with_flush(handler)
    params = list(inspect.signature(wrapped).parameters.keys())
    assert len(params) >= 2 and params[1] == "context"


def test_sync_handler_flushes_after_return(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(
        "agent_core.runtime.entrypoint._flush_telemetry", lambda: calls.append(1)
    )

    def handler(payload, context):  # noqa: ANN001, ANN202
        return {"ok": True}

    result = _wrap_with_flush(handler)({"p": 1}, {})
    assert result == {"ok": True}
    assert calls == [1]


def test_sync_handler_flushes_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(
        "agent_core.runtime.entrypoint._flush_telemetry", lambda: calls.append(1)
    )

    def handler(payload, context):  # noqa: ANN001, ANN202
        raise ValueError("boom")

    with pytest.raises(ValueError):
        _wrap_with_flush(handler)({}, {})
    assert calls == [1]


def test_sync_generator_flushes_only_after_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        "agent_core.runtime.entrypoint._flush_telemetry", lambda: calls.append(1)
    )

    def handler(payload, context):  # noqa: ANN001, ANN202
        yield "a"
        yield "b"

    gen = _wrap_with_flush(handler)({}, {})
    assert inspect.isgenerator(gen)
    assert calls == []  # not flushed until the stream is consumed
    assert list(gen) == ["a", "b"]
    assert calls == [1]


def test_async_handler_flushes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(
        "agent_core.runtime.entrypoint._flush_telemetry", lambda: calls.append(1)
    )

    async def handler(payload, context):  # noqa: ANN001, ANN202
        return {"ok": 1}

    wrapped = _wrap_with_flush(handler)
    assert asyncio.iscoroutinefunction(wrapped)
    assert asyncio.run(wrapped({}, {})) == {"ok": 1}
    assert calls == [1]


def test_async_generator_flushes_only_after_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        "agent_core.runtime.entrypoint._flush_telemetry", lambda: calls.append(1)
    )

    async def handler(payload, context):  # noqa: ANN001, ANN202
        yield 1
        yield 2

    wrapped = _wrap_with_flush(handler)
    assert inspect.isasyncgenfunction(wrapped)

    async def _collect() -> list:
        out = []
        async for item in wrapped({}, {}):
            out.append(item)
        return out

    assert asyncio.run(_collect()) == [1, 2]
    assert calls == [1]


def test_flush_telemetry_is_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    """force_flush is called per provider; any failure is swallowed."""
    from types import SimpleNamespace

    from agent_core.runtime import entrypoint as ep

    flushed = []

    def force_flush(timeout_millis=None):  # noqa: ANN001, ANN202
        flushed.append(timeout_millis)

    fake_module = SimpleNamespace(
        get_logger_provider=lambda: SimpleNamespace(force_flush=force_flush),
        get_meter_provider=lambda: SimpleNamespace(force_flush=force_flush),
        get_tracer_provider=lambda: SimpleNamespace(force_flush=force_flush),
    )
    monkeypatch.setattr(ep.importlib, "import_module", lambda _name: fake_module)

    ep._flush_telemetry()  # must not raise
    assert flushed == [5000, 5000, 5000]
